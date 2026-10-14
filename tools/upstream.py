#!/usr/bin/env python3
"""Propose upstream schema updates (docs/specs/upstream.md, UPD-1 to UPD-4).

Usage: tools/upstream.py [--dry-run]

Needs gh with GH_TOKEN and git; a pull request also needs ./check (docker).
--dry-run does every read and prints the pull requests and issues it would
open or update, without writing anything, ./check included.
"""

import argparse
import base64
import copy
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com/"
REPO = API + "repos/{owner}/{repo}/"  # gh fills in the repository of ROOT
GITHUB = re.compile(r"https://github\.com/([^/]+/[^/]+)/(tree|blob)/([^/]+)/(.+)")
TERRAFORM = re.compile(r"https://registry\.terraform\.io/providers/([^/]+/[^/]+)/([^/]+)")
ANNOTATIONS = ("$id", "$schema", "title", "description")
COMPONENTS = "#/components/schemas/"


class Loader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    """Safe loader that reads a plain = (YAML 1.1 value key, as in matcher enums) as a string."""


Loader.add_constructor("tag:yaml.org,2002:value", Loader.construct_yaml_str)


def get(url):
    """Every network read: the GitHub API through gh, anything else over HTTPS."""
    if url.startswith(API):
        return subprocess.run(["gh", "api", url.removeprefix(API)], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def classify(url):
    """(row, release repository, ref) of a source per the UPD-1 table, None if unchecked."""
    if m := TERRAFORM.fullmatch(url):
        return "terraform", m[1], m[2]
    if not (m := GITHUB.fullmatch(url)):
        return None
    repo, ref = m[1], m[3]
    if repo == "yannh/kubernetes-json-schema":
        return "kubernetes", "kubernetes/kubernetes", ref
    return ("commit" if re.fullmatch(r"[0-9a-f]{40}", ref) else "tag"), repo, ref


def semver(tag, prefix=None):
    """Version tuple of a tag after prefix (any non-digit prefix if None), None if it is no plain version."""
    m = re.fullmatch((r"\D*" if prefix is None else re.escape(prefix)) + r"(\d+(?:\.\d+)*)", tag)
    return tuple(map(int, m[1].split("."))) if m else None


def tag_prefix(row, ref):
    """Tag prefix the current ref uses (v, edge-, none); None, any prefix, for a ref that is a commit."""
    return None if row in ("commit", "kubernetes") else re.match(r"\D*", ref)[0]


def latest(row, repo, ref):
    """Newest release of a source's upstream with the prefix of its ref, None if there is none."""
    if row == "terraform":
        tags = json.loads(get(f"https://registry.terraform.io/v1/providers/{repo}"))["versions"]
    else:
        releases = json.loads(get(f"{API}repos/{repo}/releases?per_page=100"))
        tags = [r["tag_name"] for r in releases if not r["draft"] and not r["prerelease"]]
        if not releases:
            tags = [t["name"] for t in json.loads(get(f"{API}repos/{repo}/tags?per_page=100"))]
    tags = [t for t in tags if semver(t, tag_prefix(row, ref))]
    return max(tags, key=lambda t: semver(t, tag_prefix(row, ref))) if tags else None


def not_regenerable(row, url):
    """Why a source's schemas cannot be regenerated (UPD-4), None if they can."""
    if row in ("terraform", "kubernetes"):
        return {"terraform": "Terraform extract", "kubernetes": "kubernetes-json-schema"}[row]
    if url.endswith(".go"):
        return "Go code"
    if re.search(r"/templates(/|$)", url):
        return "Helm templates"
    return None


def crd_schemas(url):
    """({<kind>_<version>.json: openAPIV3Schema}, {(group, plural): (crds/<file>, content)}) of the CRDs in the YAML files at or under a GitHub source.

    A CRD file is the upstream file if that holds only this CRD and fits 1 MiB, else the CRD as compact JSON (registry QA-12).
    """
    repo, kind, ref, path = GITHUB.fullmatch(url).groups()
    files, dirs = ([path], []) if kind == "blob" else ([], [path])
    while dirs:
        for e in json.loads(get(f"{API}repos/{repo}/contents/{dirs.pop()}?ref={ref}")):
            if e["type"] == "dir":
                dirs.append(e["path"])
            elif e["name"].endswith((".yaml", ".yml")):
                files.append(e["path"])
    schemas, crds = {}, {}
    for f in sorted(files):
        raw = get(f"https://raw.githubusercontent.com/{repo}/{ref}/{f}")
        docs = [d for d in yaml.load_all(raw, Loader=Loader) if d is not None]
        for doc in docs:
            if isinstance(doc, dict) and doc.get("kind") == "CustomResourceDefinition" and doc.get("spec", {}).get("versions"):  # patches carry no versions
                for v in doc["spec"]["versions"]:
                    if "openAPIV3Schema" in v.get("schema", {}):
                        schemas[f"{doc['spec']['names']['kind'].lower()}_{v['name']}.json"] = v["schema"]["openAPIV3Schema"]
                plural = doc["spec"]["names"]["plural"]
                if len(docs) == 1 and len(raw) <= 1 << 20:
                    crds[doc["spec"]["group"], plural] = (f"crds/{plural}.yaml", raw.decode())
                else:
                    crds[doc["spec"]["group"], plural] = (f"crds/{plural}.json", json.dumps(doc, separators=(",", ":")) + "\n")
    return schemas, crds


def inline(node, components, definitions):
    """Point the component references in node to definitions, copying each referenced component there once."""
    if isinstance(node, list):
        for sub in node:
            inline(sub, components, definitions)
    elif isinstance(node, dict):
        if str(node.get("$ref")).startswith(COMPONENTS):
            name = node["$ref"].removeprefix(COMPONENTS)
            node["$ref"] = "#/definitions/" + name
            if name not in definitions:
                definitions[name] = copy.deepcopy(components[name])
                inline(definitions[name], components, definitions)
        for sub in node.values():
            inline(sub, components, definitions)


def openapi_schemas(url):
    """{<kind>_<version>.json: schema} of the kinds in the OpenAPI v3 document at a GitHub source, referenced components under definitions."""
    repo, _, ref, path = GITHUB.fullmatch(url).groups()
    components = json.loads(get(f"https://raw.githubusercontent.com/{repo}/{ref}/{path}")).get("components", {}).get("schemas", {})
    schemas = {}
    for component in components.values():
        for gvk in component.get("x-kubernetes-group-version-kind", []):
            schema, definitions = copy.deepcopy(component), {}
            inline(schema, components, definitions)
            schema["definitions"] = dict(sorted(definitions.items()))
            schemas[f"{gvk['kind'].lower()}_{gvk['version']}.json"] = schema
    return schemas


def close(schema):
    """additionalProperties: false on every node with properties, like kubeconform strict mode."""
    if not isinstance(schema, dict):
        return
    if "properties" in schema and "additionalProperties" not in schema and not schema.get("x-kubernetes-preserve-unknown-fields"):
        schema["additionalProperties"] = False
    for sub in [*schema.get("properties", {}).values(), *schema.get("definitions", {}).values()]:
        close(sub)
    close(schema.get("items"))
    close(schema.get("additionalProperties"))


def ordered(node):
    """Whether every object in a JSON value has its keys sorted."""
    if isinstance(node, dict):
        return list(node) == sorted(node) and all(ordered(v) for v in node.values())
    return all(ordered(v) for v in node) if isinstance(node, list) else True


def render(schema, committed):
    """The JSON Schema file for one openAPIV3Schema, with the top-level annotations and layout of the committed file."""
    old = json.loads(committed)
    props = schema.setdefault("properties", {})
    for key, sub in (("apiVersion", {"type": "string"}), ("kind", {"type": "string"}), ("metadata", {"type": "object"})):
        props.setdefault(key, sub)
    close(schema)
    schema.update((k, old[k]) for k in ANNOTATIONS if k in old)
    sort = ordered(old)
    if not sort:
        schema = {k: schema[k] for k in dict.fromkeys([*old, *schema]) if k in schema}
    lines = committed.splitlines()
    if len(lines) == 1:
        return json.dumps(schema, separators=(",", ":"), sort_keys=sort) + "\n"
    return json.dumps(schema, indent=len(lines[1]) - len(lines[1].lstrip(" ")), sort_keys=sort) + "\n"


def regenerate(urls, committed, group):
    """({file: content}, [missing files]) for a group's committed files {name: content} from the CRDs or OpenAPI documents at urls.

    A crds/<plural> file whose CRD has the other form (QA-12) at urls maps to None, next to the file in that form.
    """
    schemas, crds = {}, {}
    for url in urls:
        more, more_crds = (openapi_schemas(url), {}) if url.endswith(".json") else crd_schemas(url)
        schemas.update(more)
        crds.update(more_crds)
    files = {n: render(schemas[n], text) for n, text in committed.items() if n in schemas}
    for n in committed:
        if n.startswith("crds/") and (crd := crds.get((group, Path(n).stem))):
            files[n] = None
            files[crd[0]] = crd[1]
    return files, [n for n in committed if n not in files]


def gate(directory, old_urls, new_urls):
    """UPD-2: (files at the new release, None) if the group reproduces, else (None, cause)."""
    committed = {p.name: p.read_text() for p in sorted(directory.glob("*.json"))}
    if not committed:
        return None, f"no schema files in {directory.name}"
    committed |= {f"crds/{p.name}": p.read_bytes().decode() for p in sorted(directory.glob("crds/*")) if p.is_file()}
    files, missing = regenerate(old_urls, committed, directory.name)
    differ = [f"no CRD for {n}" for n in missing] + [f"{n} differs" for n, text in committed.items() if n in files and files[n] != text]
    if differ:
        return None, "does not reproduce: " + ", ".join(differ)
    files, missing = regenerate(new_urls, committed, directory.name)
    if missing:
        return None, "missing at the new release: " + ", ".join(missing)
    return files, None


def outdated(gen):
    """UPD-1 and UPD-2 for one generator: the groups with a newer release, each with files or cause."""
    sources = yaml.load((ROOT / gen / "schemas" / "sources.yaml").read_text(), Loader=yaml.BaseLoader)
    updates = []
    for group, entry in sources.items():
        old = pairs(entry)
        new, reasons = [], []
        for url, version in old:
            c = classify(url)
            tag = c and latest(*c)
            reasons.append(not_regenerable(c[0], url) if c else "unchecked source")
            if not c:
                print(f"{gen} {group}: unchecked source {url}")
            elif not tag:
                print(f"{gen} {group}: {version}, {c[1]} has no release or tag")
            else:
                print(f"{gen} {group}: current {version}, latest {tag}")
            if tag and ((cur := semver(version)) is None or semver(tag, tag_prefix(c[0], c[2])) > cur):
                new.append((url.replace(f"/{c[2]}/", f"/{tag}/", 1), tag if version == c[2] else re.fullmatch(r"\D*(.*)", tag)[1]))
            else:
                new.append((url, version))
        if new == old:
            continue
        cause = next((f"not regenerable: {r}" for r in reasons if r), None)
        files = None
        if not cause:
            files, cause = gate(ROOT / gen / "schemas" / group, [u for u, _ in old], [u for u, _ in new])
        print(f"{gen} {group}: {cause or 'regenerates and reproduces'}")
        updates.append({"group": group, "software": entry["software"], "old": old, "new": new, "files": files, "cause": cause})
    return updates


def pairs(entry):
    """[(url, version)] of a sources.yaml entry; one version applies to every URL."""
    urls, versions = entry["source"].split(), entry["version"].split(" / ")
    return list(zip(urls, versions * len(urls) if len(versions) == 1 else versions, strict=True))


def label(update, key):
    versions = [v for _, v in update[key]]
    return versions[0] if len(set(versions)) == 1 else " / ".join(versions)


def subject(updates):
    """'<software> <version>' of every update, each once."""
    return ", ".join(dict.fromkeys(f"{u['software']} {label(u, 'new')}" for u in updates))


def issue_title(gen, updates):
    return f"[upstream] {gen}: {subject(updates)}"


def pr_title(gen, updates):
    return f"feat({gen}): update schemas to {subject(updates)}"


def body(updates, tail, pr):
    """Pull request (UPD-3) or issue (UPD-4) body: versions per group, causes, tail of ./check."""
    lines = ["| Group | Software | Before | After |" + ("" if pr else " Cause |"), "|---|---|---|---|" + ("" if pr else "---|")]
    for u in updates:
        lines.append(f"| `{u['group']}` | {u['software']} | {label(u, 'old')} | {label(u, 'new')} |" + ("" if pr else f" {u['cause'] or 'regenerates'} |"))
    if pr:
        lines += ["", "Opened by the upstream workflow. Before merging, check the generator's defaults and code against the new release, and set the generator version and CHANGELOG entry."]
    if tail:
        lines += ["", "Tail of `./check`:", "", "```", tail, "```"]
    return "\n".join(lines) + "\n"


def bump_sources(text, update):
    """sources.yaml text with the group's version and source replaced, comments kept."""
    out, group = [], None
    for line in text.splitlines(keepends=True):
        if m := re.match(r"([^\s#][^:]*):\s*$", line):
            group = m[1]
        elif group == update["group"] and line.startswith("  version: "):
            line = f"  version: {label(update, 'new')}\n"
        elif group == update["group"] and line.startswith("  source: "):
            line = f"  source: {' '.join(u for u, _ in update['new'])}\n"
        out.append(line)
    return "".join(out)


def bump_readme(text, updates):
    """README text with the old versions on its "Built for" lines replaced by the new ones."""
    lines = text.splitlines(keepends=True)
    for u in updates:
        for (_, old), (_, new) in zip(u["old"], u["new"]):
            pattern = re.compile(rf"(?<![\d.]){re.escape(old)}(?!\d|\.\d)")
            lines = [pattern.sub(new, line) if "Built for" in line else line for line in lines]
    return "".join(lines)


def run(*cmd):
    return subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def propose(gen, updates, pr, dry_run):
    """UPD-3 for the groups that regenerate; the tail of a failing ./check, their cause then, else None."""
    branch = f"upstream/{gen}"
    sources = (ROOT / gen / "schemas" / "sources.yaml").read_text()
    for u in updates:
        sources = bump_sources(sources, u)
    title, change = pr_title(gen, updates), f"pull request #{pr['number']}" if pr else "a pull request"
    if pr and base64.b64decode(json.loads(get(f"{REPO}contents/{gen}/schemas/sources.yaml?ref={branch}"))["content"]).decode() == sources:
        print(f"{gen}: {change} already proposes these versions")
        return None
    if dry_run:
        print(f"{gen}: would {'update' if pr else 'open'} {change} from {branch} if ./check passes: {title}")
        print(body(updates, None, True))
        return None
    for u in updates:
        for name, text in u["files"].items():
            path = ROOT / gen / "schemas" / u["group"] / name
            if text is None:
                path.unlink()
            else:
                path.write_text(text)
    (ROOT / gen / "schemas" / "sources.yaml").write_text(sources)
    readme = ROOT / gen / "README.md"
    readme.write_text(bump_readme(readme.read_text(), updates))
    check = subprocess.run(["./check", gen], cwd=ROOT, check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(check.stdout)
    tail = "\n".join(check.stdout.splitlines()[-30:])
    if check.returncode:
        for u in updates:
            u["cause"] = "`./check` fails"
        return tail
    run("git", "checkout", "-B", branch)
    run("git", "add", "--", gen)
    run("git", "commit", "-m", title)
    run("git", "push", "--force", "origin", branch)
    text = body(updates, tail, True)
    if pr:
        run("gh", "pr", "edit", str(pr["number"]), "--title", title, "--body", text)
    else:
        run("gh", "pr", "create", "--base", "main", "--head", branch, "--title", title, "--body", text)
    print(f"{gen}: {'updated' if pr else 'opened'} {change}: {title}")
    return None


def report(gen, updates, tail, issues, dry_run):
    """UPD-4 for the groups that cannot be proposed."""
    title, text = issue_title(gen, updates), body(updates, tail, False)
    issue = next((i for i in issues if i["title"].startswith(f"[upstream] {gen}: ")), None)
    change = f"issue #{issue['number']}" if issue else "an issue"
    if issue and issue["title"] == title and (issue["body"] or "") == text:
        print(f"{gen}: {change} is up to date")
    elif dry_run:
        print(f"{gen}: would {'update' if issue else 'open'} {change}: {title}")
        print(text)
    elif issue:
        run("gh", "issue", "edit", str(issue["number"]), "--title", title, "--body", text)
        print(f"{gen}: updated {change}: {title}")
    else:
        run("gh", "issue", "create", "--title", title, "--body", text)
        print(f"{gen}: opened an issue: {title}")


def act(gen, updates, prs, issues, dry_run):
    """A pull request for the groups that regenerate, an issue for the rest (UPD-3, UPD-4)."""
    tail = None
    if ready := [u for u in updates if not u["cause"]]:
        tail = propose(gen, ready, prs.get(f"upstream/{gen}"), dry_run)
    if rest := [u for u in updates if u["cause"]]:
        report(gen, rest, tail, issues, dry_run)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="read only, print the intended pull requests and issues")
    args = parser.parse_args()
    pulls = json.loads(get(f"{REPO}pulls?state=open&per_page=100"))
    prs = {p["head"]["ref"]: p for p in pulls if (p["head"]["repo"] or {}).get("full_name") == p["base"]["repo"]["full_name"]}
    issues = [i for i in json.loads(get(f"{REPO}issues?state=open&per_page=100")) if "pull_request" not in i]
    base = run("git", "rev-parse", "HEAD")
    failed = []
    for sources in sorted(ROOT.glob("*/schemas/sources.yaml")):
        gen = sources.parts[-3]
        try:
            if updates := outdated(gen):
                act(gen, updates, prs, issues, args.dry_run)
        except (subprocess.CalledProcessError, OSError, ValueError, KeyError, yaml.YAMLError) as e:
            print(f"{gen}: failed: {e} {getattr(e, 'stderr', '') or ''}", file=sys.stderr)
            failed.append(gen)
        finally:
            if not args.dry_run:
                run("git", "checkout", "-f", "--detach", base)
    if failed:
        print("failed: " + ", ".join(failed), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
