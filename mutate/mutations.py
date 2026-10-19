"""Matching and actions of the mutate generator, without Kapitan (docs/specs/mutate.md)."""

import copy
import os

import yaml

ACTIONS = ("merge", "json6902", "delete", "images")
MUTATION_KEYS = {"match", "expects", "merge_lists", *ACTIONS}
MATCH_KEYS = {"apiVersion", "kind", "name", "namespace", "labels"}
IMAGE_KEYS = {"name", "tag", "digest"}
OP_KEYS = {
    "add": {"path", "value"},
    "remove": {"path"},
    "replace": {"path", "value"},
    "move": {"from", "path"},
    "copy": {"from", "path"},
    "test": {"path", "value"},
}
POD_SPEC = {
    "Pod": ("spec",),
    "Deployment": ("spec", "template", "spec"),
    "StatefulSet": ("spec", "template", "spec"),
    "DaemonSet": ("spec", "template", "spec"),
    "Job": ("spec", "template", "spec"),
    "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
}


class MutationError(ValueError):
    pass


class Loader(yaml.SafeLoader):
    pass


# A plain "=" is the YAML 1.1 value key, which the safe loader cannot construct.
Loader.add_constructor("tag:yaml.org,2002:value", Loader.construct_yaml_str)


class Dumper(yaml.SafeDumper):
    pass


def _str(dumper, value):
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


Dumper.add_representer(str, _str)


def load(text):
    loader = Loader(text)
    try:
        docs = []
        while loader.check_data():
            doc = loader.get_data()
            if doc is not None:
                docs.append(doc)
        return docs
    finally:
        loader.dispose()


def dump(docs):
    return yaml.dump_all(docs, Dumper=Dumper, sort_keys=False, default_flow_style=False)


def read_files(root):
    """{relative path: [documents]} of every .yaml and .yml file below root."""
    files = {}
    for folder, dirs, names in os.walk(root):
        dirs.sort()
        for name in sorted(names):
            if not name.endswith((".yaml", ".yml")):
                continue
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, root)
            with open(path, encoding="utf-8") as f:
                try:
                    files[rel] = load(f.read())
                except yaml.YAMLError as e:
                    raise MutationError(f"mutate: {rel}: not YAML: {e}") from e
    return files


def check_entries(entries):
    """Fail unless every kadet compile entry that passes mutations writes plain output."""
    for entry in entries:
        if (
            entry.get("input_type") == "kadet"
            and "mutations" in (entry.get("input_params") or {})
            and entry.get("output_type") != "plain"
        ):
            raise MutationError(
                f"mutate: the compile entry for {entry.get('output_path')} needs output_type: plain,"
                f" has {entry.get('output_type', 'yaml')}"
            )


def fail(mid, message, file=None):
    where = f" {file}:" if file else ""
    raise MutationError(f"mutate: mutation {mid}:{where} {message}")


def check(mid, m):
    if not isinstance(m, dict):
        fail(mid, "must be a map")
    unknown = set(m) - MUTATION_KEYS
    if unknown:
        fail(mid, f"unknown keys {sorted(unknown)}")
    match = m.get("match")
    if not isinstance(match, dict) or not match:
        fail(mid, "match must be a non-empty map")
    unknown = set(match) - MATCH_KEYS
    if unknown:
        fail(mid, f"unknown match keys {sorted(unknown)}")
    for key, value in match.items():
        if key == "labels":
            if not isinstance(value, dict) or not value or not all(isinstance(v, str) for v in value.values()):
                fail(mid, "match.labels must be a non-empty map of strings")
        elif not isinstance(value, str):
            fail(mid, f"match.{key} must be a string")
    actions = [a for a in ACTIONS if a in m]
    if len(actions) != 1:
        fail(mid, f"needs exactly one of {', '.join(ACTIONS)}, has {actions or 'none'}")
    action = actions[0]
    expects = m.get("expects", "1+")
    if expects not in ("1+", "0+") and not (type(expects) is int and expects >= 0):
        fail(mid, f'expects must be "1+", "0+" or a non-negative integer, not {expects!r}')
    if "merge_lists" in m:
        lists = m["merge_lists"]
        if action != "merge":
            fail(mid, "merge_lists needs merge")
        if not isinstance(lists, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in lists.items()):
            fail(mid, "merge_lists must map list field names to key field names")
    if action == "merge" and not isinstance(m["merge"], dict):
        fail(mid, "merge must be a map")
    if action == "delete" and m["delete"] is not True:
        fail(mid, "delete must be true")
    if action == "json6902":
        ops = m["json6902"]
        if not isinstance(ops, list) or not ops:
            fail(mid, "json6902 must be a non-empty list of operations")
        for op in ops:
            if not isinstance(op, dict) or op.get("op") not in OP_KEYS:
                fail(mid, f"json6902 operation {op!r} needs op one of {', '.join(OP_KEYS)}")
            if set(op) - {"op"} != OP_KEYS[op["op"]]:
                fail(mid, f"json6902 {op['op']} takes exactly {sorted(OP_KEYS[op['op']])}, has {sorted(set(op) - {'op'})}")
            if not isinstance(op["path"], str) or not isinstance(op.get("from", ""), str):
                fail(mid, "json6902 path and from must be strings")
    if action == "images":
        images = m["images"]
        if not isinstance(images, dict) or not images:
            fail(mid, "images must be a non-empty map")
        for name, new in images.items():
            if not isinstance(new, dict) or not new or set(new) - IMAGE_KEYS:
                fail(mid, f"images.{name} takes one or more of name, tag, digest")
            if not all(isinstance(v, str) and v for v in new.values()):
                fail(mid, f"images.{name}: values must be non-empty strings")


def matches(match, doc):
    if not isinstance(doc, dict):
        return False
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    labels = meta.get("labels") if isinstance(meta.get("labels"), dict) else {}
    for key, want in match.items():
        if key == "labels":
            if any(labels.get(k) != v for k, v in want.items()):
                return False
        elif key == "kind" and want == "*":
            continue
        elif key in ("apiVersion", "kind"):
            if doc.get(key) != want:
                return False
        elif meta.get(key) != want:
            return False
    return True


def merge(target, patch, lists, mid, file):
    """RFC 7386 merge of patch into target, with keyed merge for the lists in lists."""
    if not isinstance(target, dict):
        target = {}
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        elif isinstance(value, dict):
            target[key] = merge(target.get(key), value, lists, mid, file)
        elif isinstance(value, list) and key in lists:
            target[key] = merge_list(target.get(key), value, key, lists, mid, file)
        else:
            target[key] = copy.deepcopy(value)
    return target


def merge_list(target, patch, field, lists, mid, file):
    key = lists[field]
    target = target if isinstance(target, list) else []
    index = {}
    for item in target:
        if isinstance(item, dict) and key in item:
            if item[key] in index:
                fail(mid, f"{field}: duplicate {key} {item[key]!r} in the document", file)
            index[item[key]] = item
    seen = set()
    for item in patch:
        if not isinstance(item, dict) or key not in item:
            fail(mid, f"{field}: every merge item needs {key}", file)
        if item[key] in seen:
            fail(mid, f"{field}: duplicate {key} {item[key]!r} in the merge", file)
        seen.add(item[key])
        if item[key] in index:
            merge(index[item[key]], item, lists, mid, file)
        else:
            target.append(merge({}, item, lists, mid, file))
    return target


def pointer(path, mid, file):
    if path == "":
        return []
    if not path.startswith("/"):
        fail(mid, f"json6902 path {path!r} must be empty or start with /", file)
    return [t.replace("~1", "/").replace("~0", "~") for t in path[1:].split("/")]


def locate(holder, tokens, mid, file, path):
    """The container and key the last token names; holder is [document], tokens start with 0."""
    node, key = holder, tokens[0]
    for token in tokens[1:]:
        node, key = step(node, key, mid, file, path), token
    return node, key


def step(node, key, mid, file, path):
    child = get(node, key, mid, file, path)
    if not isinstance(child, (dict, list)):
        fail(mid, f"json6902 path {path!r} does not exist", file)
    return child


def list_index(node, key, mid, file, path, append=False):
    if isinstance(key, int):
        return key
    if append and key == "-":
        return len(node)
    if not key.isdigit() or (key.startswith("0") and key != "0"):
        fail(mid, f"json6902 path {path!r}: {key!r} is not a list index", file)
    return int(key)


def get(node, key, mid, file, path):
    if isinstance(node, dict):
        if key not in node:
            fail(mid, f"json6902 path {path!r} does not exist", file)
        return node[key]
    i = list_index(node, key, mid, file, path)
    if i >= len(node):
        fail(mid, f"json6902 path {path!r} does not exist", file)
    return node[i]


def add(node, key, value, mid, file, path):
    if isinstance(node, dict):
        node[key] = value
        return
    i = list_index(node, key, mid, file, path, append=True)
    if i > len(node):
        fail(mid, f"json6902 path {path!r} does not exist", file)
    node.insert(i, value)


def remove(node, key, mid, file, path):
    value = get(node, key, mid, file, path)
    if isinstance(node, dict):
        del node[key]
    else:
        del node[list_index(node, key, mid, file, path)]
    return value


def json_equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(json_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(json_equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b


def json6902(doc, ops, mid, file):
    holder = [doc]
    for op in ops:
        path = op["path"]
        node, key = locate(holder, [0, *pointer(path, mid, file)], mid, file, path)
        name = op["op"]
        if name == "add":
            add(node, key, copy.deepcopy(op["value"]), mid, file, path)
        elif name == "remove":
            remove(node, key, mid, file, path)
        elif name == "replace":
            get(node, key, mid, file, path)
            if isinstance(node, dict):
                node[key] = copy.deepcopy(op["value"])
            else:
                node[list_index(node, key, mid, file, path)] = copy.deepcopy(op["value"])
        elif name == "test":
            if not json_equal(get(node, key, mid, file, path), op["value"]):
                fail(mid, f"json6902 test of {path!r} failed", file)
        else:
            source = op["from"]
            if name == "move" and path.startswith(source + "/"):
                fail(mid, f"json6902 move from {source!r} into itself", file)
            snode, skey = locate(holder, [0, *pointer(source, mid, file)], mid, file, source)
            if name == "move":
                value = remove(snode, skey, mid, file, source)
            else:
                value = copy.deepcopy(get(snode, skey, mid, file, source))
            node, key = locate(holder, [0, *pointer(path, mid, file)], mid, file, path)
            add(node, key, value, mid, file, path)
    if not holder:
        fail(mid, "json6902 removed the document", file)
    return holder[0]


def split_image(image):
    """name, tag, digest of an image reference; tag and digest may be None."""
    name, _, digest = image.partition("@")
    tag = None
    if ":" in name.rsplit("/", 1)[-1]:
        name, tag = name.rsplit(":", 1)
    return name, tag, digest or None


def set_images(doc, images, used):
    spec = doc
    for key in POD_SPEC.get(doc.get("kind"), ()):
        spec = spec.get(key) if isinstance(spec, dict) else None
    if spec is doc or not isinstance(spec, dict):
        return
    for field in ("initContainers", "containers"):
        for container in spec.get(field) or []:
            if not isinstance(container, dict) or not isinstance(container.get("image"), str):
                continue
            name, tag, digest = split_image(container["image"])
            new = images.get(name)
            if new is None:
                continue
            used.add(name)
            name = new.get("name", name)
            if "tag" in new or "digest" in new:
                tag, digest = new.get("tag"), new.get("digest")
            container["image"] = name + (f":{tag}" if tag else "") + (f"@{digest}" if digest else "")


def identity(doc):
    meta = doc.get("metadata") if isinstance(doc, dict) else None
    return (
        isinstance(doc, dict)
        and isinstance(doc.get("apiVersion"), str)
        and isinstance(doc.get("kind"), str)
        and isinstance(meta, dict)
        and isinstance(meta.get("name"), str)
        and bool(meta["name"])
    )


def apply(files, mutations):
    """Apply mutations to {path: [documents]}; return {path: text} of every touched file."""
    if not isinstance(mutations, dict):
        raise MutationError("mutate: mutations must be a map of id to mutation")
    for mid, m in mutations.items():
        check(mid, m)
    ids = sorted(mutations, key=str)
    order = [i for i in ids if "delete" not in mutations[i]] + [i for i in ids if "delete" in mutations[i]]
    files = {path: copy.deepcopy(docs) for path, docs in files.items()}
    touched, deleted_by = set(), {}
    for mid in order:
        m = mutations[mid]
        count, used = 0, set()
        for path in sorted(files):
            docs = files[path]
            for i, doc in list(enumerate(docs)):
                if not matches(m["match"], doc):
                    continue
                count += 1
                if "delete" in m:
                    touched.add(path)
                    docs[i] = None
                    deleted_by.setdefault(path, set()).add(str(mid))
                    continue
                before = copy.deepcopy(doc)
                if "merge" in m:
                    doc = merge(doc, m["merge"], m.get("merge_lists", {}), mid, path)
                elif "json6902" in m:
                    doc = json6902(doc, m["json6902"], mid, path)
                else:
                    set_images(doc, m["images"], used)
                if not identity(doc):
                    fail(mid, "result lost apiVersion, kind or metadata.name", path)
                if doc != before:
                    touched.add(path)
                docs[i] = doc
            files[path] = [d for d in docs if d is not None]
        expects = m.get("expects", "1+")
        if (expects == "1+" and count < 1) or (type(expects) is int and count != expects):
            fail(mid, f"expects {expects}, matched {count}")
        if "images" in m and count:
            unused = sorted(set(m["images"]) - used)
            if unused:
                fail(mid, f"images {unused} match no container of the {count} matched documents")
    out = {}
    for path in sorted(touched):
        if files[path]:
            out[path] = dump(files[path])
        else:
            out[path] = f"# all objects removed by mutation {', '.join(sorted(deleted_by[path]))}\n"
    return out
