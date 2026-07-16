"""Re-tag code fences in a converted book .md.

MinerU's fence language ID is unreliable (Java->swift/erlang, many bare ```code). Pygments
guess_lexer and guesslang both fail on short snippets. So we use a precision-first precedence
tuned to technical-book corpora (JVM, Python, Go, shell, infra configs):
  1. `# file: x.ext` comment  -> extension is near-certain (strongest)
  2. an existing SPECIFIC, valid MinerU tag -> keep it (it is mostly right: ruby, yaml, json, shell)
  3. keyword heuristic -> use when confident
     (http/ruby/yaml/dockerfile/xml/json/java/python/sql/bash/ini/properties; precision-first,
      Java gated on JVM-specific signals so Rust/C aren't mislabeled by a bare semicolon)
  4. else `text`
Never touches ```mermaid. Idempotent.
"""
import collections
import re

EXT = {'py': 'python', 'js': 'javascript', 'ts': 'typescript', 'yaml': 'yaml', 'yml': 'yaml',
       'json': 'json', 'sh': 'bash', 'bash': 'bash', 'sql': 'sql', 'rb': 'ruby', 'go': 'go',
       'java': 'java', 'toml': 'toml', 'ini': 'ini', 'env': 'ini', 'cfg': 'ini', 'conf': 'ini',
       'html': 'html', 'css': 'css', 'xml': 'xml', 'txt': 'text', 'dockerfile': 'dockerfile',
       'proto': 'protobuf', 'properties': 'properties', 'kt': 'kotlin', 'kts': 'kotlin',
       'rs': 'rust', 'c': 'c', 'h': 'c', 'cpp': 'cpp', 'cc': 'cpp', 'cxx': 'cpp', 'hpp': 'cpp',
       'cs': 'csharp', 'scala': 'scala', 'php': 'php'}

# tags MinerU may emit that we treat as GENERIC (always re-detect); anything else specific we trust.
GENERIC = {'', 'code', 'txt', 'text', 'algorithm', 'plaintext', 'none'}
# normalize a few aliases to canonical fence names
CANON = {'shell': 'bash', 'sh': 'bash', 'yml': 'yaml', 'plaintext': 'text', 'txt': 'text',
         'c++': 'cpp', 'cc': 'cpp', 'props': 'properties', 'kotlin': 'kotlin'}
VALID = set(EXT.values()) | {'bash', 'python', 'yaml', 'json', 'sql', 'ruby', 'ini', 'http',
                             'dockerfile', 'javascript', 'typescript', 'go', 'java', 'toml',
                             'html', 'css', 'xml', 'text', 'protobuf', 'properties', 'kotlin',
                             'rust', 'c', 'cpp', 'csharp', 'scala', 'php'}


def heuristic(body: str) -> str:
    b = body.strip()
    lines = [l for l in b.split("\n") if l.strip()]
    first = lines[0] if lines else ""
    # 1. http: block must START with a request line, or be a header block
    if re.match(r'(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+\S+', first) or re.match(r'HTTP/\d', first):
        return "http"
    if re.match(r'(Authorization|Content-Type|Host|Accept|Cookie|User-Agent):\s', first):
        return "http"
    # 2. ruby before python (shared `def`)
    if re.search(r'params\[:|=>|\bputs\b|\.each do\b', b):
        return "ruby"
    # 3. strong yaml / k8s / openapi markers only
    if re.search(r'^\s*(apiVersion|kind|openapi|swagger|paths|components|info|servers|security|schemas|metadata|spec):', b, re.M):
        return "yaml"
    # 4. dockerfile
    if re.search(r'^(FROM|RUN|CMD|ENTRYPOINT|COPY|WORKDIR)\s', b, re.M):
        return "dockerfile"
    # 5. xml (pom.xml / CDI beans / any well-formed tag pair) — before json
    if (re.match(r'\s*<\?xml', b)
            or re.search(r'^\s*</?(project|dependency|dependencies|groupId|artifactId|version|parent|plugin|plugins|build|configuration|profiles|beans|web-app|servlet|bean)\b', b, re.M)
            or (re.match(r'\s*<[A-Za-z]', b) and re.search(r'</[A-Za-z][\w:.-]*>', b))):
        return "xml"
    # 6. json: starts with { or [ and has "key": pairs (not a bare URL/placeholder)
    if re.match(r'\s*[\{\[]', b) and re.search(r'"\w+"\s*:', b):
        return "json"
    # 7. java / JVM — BEFORE python (Java `class`/`import` would otherwise hit the python branch).
    #    Precision-first: require a Java-specific signal, not just a semicolon (else Rust/C mislabel).
    if (re.search(r'^\s*@[A-Z]\w+', b, re.M)                                             # CapCamel annotation (@Inject, @ConfigProperty)
            or re.search(r'\b(public|private|protected)\s+(static\s+|final\s+|abstract\s+|synchronized\s+)*(class|interface|enum|record|void|[A-Z][\w<>\[\]]*)\b', b)
            or re.search(r'\bimport\s+[\w.]+\s*;', b)                                     # import ...;  (semicolon = Java, not python)
            or re.search(r'\bpackage\s+[\w.]+\s*;', b)
            or re.search(r'\b(System\.out|System\.err|Objects\.hash|Optional\.|Collectors\.|Arrays\.asList|assertThat|assertEquals|assertTrue|orElseThrow)\b', b)
            or re.search(r'\b[A-Z]\w+(<[\w,<>\[\] ]+>)?\s+\w+\s*=\s*(new\s+[A-Z]|[\w.]+\(|["\'])', b)  # typed var: Account a = new/method/"..."
            or re.search(r'\b[A-Z]\w+\.[A-Z][A-Z0-9_]{2,}\b', b)):                       # enum/constant access: AccountStatus.OVERDRAWN
        return "java"
    # 8. python
    if re.search(r'\b(def|class|import|from|async\s+def|lambda)\b', b) or 'BaseModel' in b or re.search(r'@\w+\.(get|post|put|delete|patch|middleware)', b):
        return "python"
    # 9. sql
    if re.search(r'^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE\s+TABLE|ALTER\s+TABLE)\b', b, re.I | re.M):
        return "sql"
    # 10. shell: leading $/➜ prompt, a known CLI/build/k8s verb at line start, or an ENV=val-prefixed command
    if (re.search(r'(^|\n)\s*[\$➜]\s', b)
            or re.search(r'^\s*(uv|pip|pip3|curl|sudo|export|uvicorn|openssl|npm|npx|yarn|git|docker|docker-compose|podman|pytest|python3?|'
                         r'mvn|gradle|kubectl|helm|oc|minikube|make|wget|apt|apt-get|yum|dnf|brew|chmod|mkdir|cd|tar|source|'
                         r'quarkus|jbang|skaffold|kustomize|kubectx|kubens|\./mvnw|\./gradlew|\./)\s', b, re.M)
            or re.match(r'[A-Z_]{2,}=\S+\s+\w', first)):
        return "bash"
    # 11. ini: a real [section] header (alpha-started, not the [...] placeholder)
    if re.search(r'^\s*\[[A-Za-z][\w. ]*\]\s*$', b, re.M):
        return "ini"
    # 12. properties: dotted key=value (e.g. quarkus.http.port=8080, %prod.x=y)
    if (re.search(r'^\s*%?[\w-]+(\.[\w-]+)+\s*=', b, re.M)
            and '://' not in first
            and not re.search(r'^\s*(uv|pip|curl|export|git|docker|mvn|kubectl|helm)\b', b, re.M)):
        return "properties"
    # 13. generic yaml: >=2 clean `key: value` lines, no URLs, not console "N:M" output
    kv = re.findall(r'^\s*[A-Za-z][\w-]*:\s+\S', b, re.M)
    if len(kv) >= 2 and '://' not in b and not re.match(r'\s*\d+:\d+', first):
        return "yaml"
    return "text"


def detect(cur_tag: str, body: str) -> tuple[str, str]:
    m = re.search(r'#\s*file:\s*\S+\.([A-Za-z0-9]+)', body)          # 1. file-ext hint
    if m and m.group(1).lower() in EXT:
        return EXT[m.group(1).lower()], "ext"
    canon_cur = CANON.get(cur_tag, cur_tag)
    if canon_cur not in GENERIC and canon_cur in VALID:              # 2. trust specific MinerU tag
        return canon_cur, "kept"
    return heuristic(body), "kw"                                     # 3. heuristic (4. -> text)


FENCE = re.compile(r'^(```)([a-zA-Z]*)\n(.*?)^```', re.S | re.M)


def retag(md: str) -> tuple[str, list[tuple[str, str, str, str]], collections.Counter]:
    """Return (new_md, changes as (old, new, why, snippet), decision stats)."""
    changes: list[tuple[str, str, str, str]] = []
    stats: collections.Counter = collections.Counter()

    def repl(mo):
        tag, body = mo.group(2), mo.group(3)
        if tag == "mermaid" or not body.strip():
            return mo.group(0)
        new, why = detect(tag, body)
        stats[why] += 1
        if (tag or "<none>") != new:
            changes.append((tag or "<none>", new, why, body.strip().split("\n")[0][:55]))
        return f"```{new}\n{body}```"

    out = FENCE.sub(repl, md)
    return out, changes, stats
