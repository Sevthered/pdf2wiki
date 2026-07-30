# SPDX-FileCopyrightText: 2026 Sevthered <Sevthered@users.noreply.github.com>
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Re-tag code fences in a converted book .md.

MinerU's fence language ID is unreliable (Java->swift/erlang, many bare ```code). Pygments
guess_lexer and guesslang both fail on short snippets. So we use a precision-first precedence
tuned to technical-book corpora (JVM, Python, Go, C/C++, Rust, JS/TS, shell, infra configs):
  1. `# file: x.ext` comment  -> extension is near-certain (strongest)
  2. an existing SPECIFIC, valid MinerU tag -> keep it (it is mostly right: ruby, yaml, json, shell)
  3. keyword heuristic -> use when confident (http/cmake/c/cpp/rust/go/javascript/typescript/ruby/
     yaml/dockerfile/xml/json/java/python/sql/bash/ini/properties). Precision-first: the
     curly-brace/compiled families are decided BEFORE the loose keyword branches, because each of
     them has a marker no other family can produce, whereas `java`/`python`/`bash`/`ruby` key off
     tokens those languages share (`class`, `import`, `export`, `=>`).
  4. else `text`
Never touches ```mermaid. Idempotent.
"""

import collections
import re

from . import fences

EXT = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "yaml": "yaml",
    "yml": "yaml",
    "json": "json",
    "sh": "bash",
    "bash": "bash",
    "sql": "sql",
    "rb": "ruby",
    "go": "go",
    "java": "java",
    "toml": "toml",
    "ini": "ini",
    "env": "ini",
    "cfg": "ini",
    "conf": "ini",
    "html": "html",
    "css": "css",
    "xml": "xml",
    "txt": "text",
    "dockerfile": "dockerfile",
    "proto": "protobuf",
    "properties": "properties",
    "kt": "kotlin",
    "kts": "kotlin",
    "rs": "rust",
    "c": "c",
    "h": "c",
    "cpp": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "hpp": "cpp",
    "cs": "csharp",
    "scala": "scala",
    "php": "php",
}

# tags MinerU may emit that we treat as GENERIC (always re-detect); anything else specific we trust.
GENERIC = {"", "code", "txt", "text", "algorithm", "plaintext", "none"}
# normalize a few aliases to canonical fence names
CANON = {
    "shell": "bash",
    "plaintext": "text",
    "c++": "cpp",
    "c#": "csharp",
    "objective-c": "objectivec",
    "objc": "objectivec",
    "props": "properties",
    "make": "makefile",
    "mk": "makefile",
}
# Aliases that are also FILE EXTENSIONS (sh, yml, txt, js, ts, py, rs, kt, cs, cc, cxx, h, hpp,
# proto, ...) live in EXT ALONE: `detect` falls back to EXT, so one table serves both the
# `# file: x.ext` hint and the fence tag. Do not re-add them here — two tables drift.
VALID = set(EXT.values()) | {
    "bash",
    "python",
    "yaml",
    "json",
    "sql",
    "ruby",
    "ini",
    "http",
    "dockerfile",
    "javascript",
    "typescript",
    "go",
    "java",
    "toml",
    "html",
    "css",
    "xml",
    "text",
    "protobuf",
    "properties",
    "kotlin",
    "rust",
    "c",
    "cpp",
    "csharp",
    "objectivec",
    "scala",
    "php",
    # tags real books/authors emit correctly and the keyword heuristic cannot detect. Without them
    # a SPECIFIC tag falls through to `heuristic()` and lands on `text` — a downgrade. Kept
    # separate from MinerU's KNOWN-WRONG guesses (swift, erlang), which must stay re-detected.
    "makefile",
    "cmake",
    "hcl",
    "qml",
    "vhdl",
    "gherkin",
    "graphql",
    "pseudocode",
}


# --- signal sets for the curly-brace / compiled families -----------------------------------------
# Each gate needs a marker the other families here cannot produce, so a block we cannot identify
# falls through to `text` instead of borrowing a neighbour's tag. Measured on a 1674-page reference
# vault: 4175 blocks carrying an author `c`/`cpp`/`cmake`/`rust`/`go`/`javascript`/`typescript` tag
# scored 0% before these branches existed — they came out as text/python/java/ruby/properties.

# CMake: a build command in call form, or a CMake-reserved variable.
CMAKE = re.compile(
    r"^\s*(cmake_minimum_required|project|add_executable|add_library|add_subdirectory|"
    r"target_link_libraries|target_include_directories|target_compile_features|"
    r"target_compile_options|target_compile_definitions|target_sources|target_precompile_headers|"
    r"find_package|include_directories|link_directories|set_target_properties|set_property|"
    r"get_target_property|enable_testing|add_test|add_custom_command|add_custom_target|"
    r"add_compile_options|add_definitions|configure_file|cmake_policy|cmake_parse_arguments|"
    r"FetchContent_Declare|FetchContent_MakeAvailable|CPMAddPackage)\s*\(|"
    # `install(` needs a CMake keyword argument: `install() { … }` is also a shell function.
    r"^\s*install\s*\(\s*(TARGETS|FILES|DIRECTORY|PROGRAMS|EXPORT|CODE|SCRIPT|RENAME|DESTINATION)\b|"
    r"\$\{(CMAKE|PROJECT)_\w+\}|\bCMAKE_(CXX|C|BUILD|INSTALL|SOURCE|BINARY|CURRENT|EXPORT)_\w+",
    re.M | re.I,
)
# C++-only: template/namespace/stream/RAII vocabulary, C++ headers, C++ header filenames.
# NOT `new X(...)`/`delete x;` — Java, JS and Manning's pseudocode all write those verbatim.
CPP_ONLY = re.compile(
    r"\bstd::|\btemplate\s*<|\bnullptr\b|\bconstexpr\b|\bconsteval\b|\bnoexcept\b|"
    r"\busing\s+namespace\b|\bnamespace\s+\w+\s*\{|^\s*(public|private|protected)\s*:\s*$|"
    r"\b(cout|cerr|endl)\b|\boperator\s*(<<|>>|==|\[\]|\(\))|"
    r"\bauto\b\s*[&*]?\s*\w+\s*(=|:)|\bfor\s*\(\s*(const\s+)?auto\b|"
    r"~\w+\s*\(\s*\)|\b(class|struct)\s+\w+\s*:\s*(public|private|protected)\b|"
    r"#\s*include\s*[<\"][\w/.]*\.(hpp|hh|hxx|cpp|cc|cxx)[>\"]|"
    r"#\s*include\s*<c(stdio|string|math|inttypes|stdlib|assert|time|ctype|limits|stddef|stdint|"
    r"errno|float|locale|signal|wchar)>|"
    r"#\s*include\s*<(iostream|vector|string|string_view|memory|algorithm|map|set|unordered_map|"
    r"unordered_set|functional|optional|variant|thread|mutex|chrono|array|tuple|utility|numeric|"
    r"filesystem|fstream|sstream|iomanip|type_traits|concepts|ranges|span|format)>",
    re.M,
)
# C family (C or C++): the preprocessor, the C standard library, C declaration forms.
C_FAMILY = re.compile(
    r"^\s*#\s*(include|define|pragma|ifndef|ifdef|undef|elif)\b|"
    r"\b(printf|sprintf|snprintf|fprintf|scanf|malloc|calloc|realloc|memcpy|memset|strcpy|strlen)"
    r"\s*\(|\bsizeof\b|\btypedef\b|\bstruct\s+\w+\s*\{|\bint\s+main\s*\(",
    re.M,
)
# Rust: `fn`, `let mut`, attributes, bang-macros, the `use ...::` module path, `-> Result<...>`.
RUST = re.compile(
    r"\bfn\s+\w+\s*[(<]|\blet\s+mut\b|\bimpl\b[^;\n]*\{|^\s*#!?\[\w|"
    r"\bpub\s+(fn|struct|enum|mod|trait|const|static|use|type)\b|"
    r"\buse\s+(std|core|alloc|crate|super|self)::|"
    r"\b(println|eprintln|format|vec|panic|write|writeln|assert|assert_eq|assert_ne|matches|todo|"
    r"unimplemented|dbg|include_str)!\s*[\(\[]|"
    # NOT `-> bool`/`-> String`: C++ writes those as a trailing return type too.
    r"->\s*(Result|Option|Self|Vec|usize|isize|[iuf](8|16|32|64|128|size))\b|\.unwrap\(\)|"
    r"\bmatch\s+[\w.&*()\[\]]+\s*\{",
    re.M,
)
# Go: `package x` alone on a line, func/method declarations, `:=`, the error idiom, channels,
# composite literals (`[]string{…}`, `&Config{`, `map[string]int`, `make(chan …)`).
GO = re.compile(
    # `\bfunc\b`, not `\bfunc`: JavaScript's `function (…)` matches the latter.
    r"^\s*package\s+\w+\s*$|\bfunc\b\s*(\(\s*\w+\s+\*?\w+\s*\)\s*)?\w*\s*\(|:=|"
    r"\berr\s*!=\s*nil\b|\bfmt\.(Print|Sprint|Errorf|Fprint)|"
    r"\btype\s+\w+\s+(struct|interface)\s*\{|\bdefer\s+\w|\bgo\s+func\b|\bchan\s+\w|"
    r"\[\]\w+\s*\{|&\w+\{|\bmap\[[\w.\[\]*]+\]|\bmake\((\[\]|map\[|chan\b)|"
    r"\b(string|int|bool|error|byte|float64)\s*\)\s*(\(|\{|error|string|int|bool)",
    re.M,
)
# Hardware/Pascal-family guard for the Go branch: VHDL and Pascal use `:=` for assignment as well
# (`signal count : integer := 0;`), and `vhdl` is a tag books really emit. Keeping `:=` in the Go
# gate is worth guarding for rather than dropping: 72 of the reference vault's `go`-tagged blocks
# carry no other Go marker.
VHDL_PASCAL = re.compile(
    r"\bstd_logic(_vector)?\b|^\s*architecture\s+\w+\s+of\s+\w+\s+is\b|^\s*entity\s+\w+\s+is\b|"
    r"^\s*signal\s+\w+\s*:\s*\w|\bdownto\b|^\s*procedure\s+\w+\s*(\(|;)|^\s*begin\s*$",
    re.M | re.I,
)
# Makefile guard for the Go branch: Make shares Go's `:=` (`MCU := atmega2560`). Gate on Make's own
# vocabulary — a phony target, a built-in function call, or a conditional assignment — none of which
# appears in Go.
MAKEFILE = re.compile(
    # NOT `+=`: every language has `count += 1`. `?=` is Make's alone.
    r"^\s*\.PHONY\s*:|^\s*[A-Za-z_][\w.-]*\s*\?=|"
    r"\$\((CC|CXX|CPP|LD|AR|RM|MAKE|CURDIR|MAKEFILE_LIST|CFLAGS|CXXFLAGS|LDFLAGS|LDLIBS|OBJS?|"
    r"SRCS?|TARGET|BIN|"
    r"shell|wildcard|patsubst|subst|addprefix|addsuffix|notdir|dir|basename|foreach|firstword)\b|"
    # a target line followed by a TAB-indented recipe. NOT a bare ALLCAPS `:=`, which is also Go's
    # (`ID := 1234`).
    r"^[\w.%/$()-]+\s*:[^=\n]*\n\t",
    re.M,
)
# JavaScript family. `=>` alone is NOT a signal: a Ruby hashrocket (`:a => 1`) looks the same, so
# only the arrow-function shapes (`) =>`, `x => {`) count.
JS = re.compile(
    r"\b(const|let|var)\s+(\w+\s*(=|,|;|\)|$)|[{\[])|\bfunction\s*\*?\s*\w*\s*\(|"
    r"\)\s*=>|\w\s*=>\s*[\{(]|\brequire\s*\(|\bmodule\.exports\b|"
    r"\bconsole\.(log|error|warn|info|debug)\b|"
    r"\bexport\s+(default|const|let|var|function|class|interface|type|async)\b|"
    r"\bimport\s+[\w{}*,\s]+\s+from\s+['\"]|\basync\s+function\b|\bawait\s+\w|"
    # strict equality needs a left operand: `=== RUN` (go test) and `[==== ]` (progress bar) are
    # console output, and `.then(` alone is also Java's REST-assured fluent API.
    r"[\w)\]'\"][ \t]*(===|!==)[ \t]*[\w('\"\[!-]|"
    r"\b(document|window)\.\w|\bnew\s+Promise\b|\buse(State|Effect|Ref|Memo|Callback)"
    r"\s*\(",
    re.M,
)
# TypeScript refinement (and the type-only blocks that carry no JS statement at all). Deliberately
# narrow, because Java owns the two forms a wider gate would steal: `interface X {` is a Java
# interface far more often than a TS one in this corpus, and `implements Y` is Java's keyword too.
# A bare `: string` also matches an OpenAPI YAML `type: string`, so an annotation only counts when
# declaration/argument punctuation follows it. `interface`/`type` therefore has to be `export`ed or
# accompanied by one of the strong signals — see `_is_typescript`.
TS_STRONG = re.compile(
    # `type:`/`format:` are excluded keys: an OpenAPI schema writes `{ type: string, format: uuid }`,
    # which is otherwise indistinguishable from a TS property annotation.
    r"(?<!\btype)(?<!\bformat)\s*:\s*(string|number|boolean|any|unknown|never|void)(\[\])?\s*[;,)={|]|"
    r"\breadonly\s+\w|^\s*export\s+(interface|type|enum)\s+[A-Z]|"
    r"^\s*(export\s+)?enum\s+[A-Z]\w*\s*\{|"
    r"\bas\s+(const|unknown|string|number|boolean)\b|\bdeclare\s+(module|const|function|global)\b|"
    r"\b(public|private|protected)\s+(readonly\s+)?\w+\s*:\s*\w+\s*[;,)=]",
    re.M,
)
TS_DECL = re.compile(r"^\s*(export\s+)?(interface|type)\s+[A-Z]\w*\s*[{=<]", re.M)
# Guards for the families the JS gate would otherwise absorb.
# Manning's algorithm books typeset pseudocode with the assignment arrow U+2190 and with a
# brace-less `function f(x)` header. Measured over the 9189-block reference set: `←` appears in 129
# of 164 `pseudocode` blocks and 25 of the other 9025; the brace-less header in 113 `pseudocode`
# blocks and 16 others (12 of which are Manning pseudocode carrying a `python` tag). Without this
# the JS branch claims them, so allman-braced JavaScript is the accepted cost.
PSEUDOCODE = re.compile(r"[←⟵]|^\s*function\s+\w+\s*\([^)]*\)\s*$", re.M)
# An HTML page with an inline <script> is HTML, not JavaScript. Only HTML-specific element names
# count, so the later xml branch keeps pom.xml / CDI beans / web.xml. Callers additionally require
# the block to OPEN with markup: JavaScript that builds markup in a template string (`let html =
# "<h1>...</h1>"`) matches these names too, and that block is JavaScript.
HTML = re.compile(
    r"<!DOCTYPE\s+html|</(html|head|body|div|span|table|tr|td|th|ul|ol|li|form|a|p|h[1-6]|"
    r"script|style|button|select|label|nav|section|header|footer|main|article)>|"
    r"<(html|head|body|div|span|table|tr|td|th|ul|ol|li|form|script|style|img|input|button|br|hr|"
    r"h[1-6]|meta|link|nav|section|header|footer|main|article)[\s/>]",
    re.I,
)


def heuristic(body: str) -> str:
    b = body.strip()
    lines = [l for l in b.split("\n") if l.strip()]
    first = lines[0] if lines else ""
    # 1. http: block must START with a request line, or be a header block
    if re.match(r"(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+\S+", first) or re.match(
        r"HTTP/\d", first
    ):
        return "http"
    if re.match(r"(Authorization|Content-Type|Host|Accept|Cookie|User-Agent):\s", first):
        return "http"
    # 2. a block that OPENS with a shell prompt is a terminal session, whatever language its output
    #    quotes (`$ diff a.go b.go` prints Go source). It must be the first line: books also print a
    #    program's output as a trailing `$ …` line inside the source block, and that block is source.
    #    Only the prompt form `$ `/`➜ ` counts, so `$(CURDIR)` and PHP's `$x` do not.
    if re.match(r"[ \t]*[$➜][ \t]", first):
        return "bash"
    # 3. pseudocode: an assignment arrow, or a brace-less `function f(x)` header, means the block is
    #    a book's algorithm listing whatever C-ish syntax it borrows. Must precede the brace
    #    families, which would claim it.
    if PSEUDOCODE.search(b):
        return "pseudocode"
    # 4. html: only when the block OPENS with markup, so JS that assembles markup in a template
    #    string stays JS. Before the code families because a server-side template mixes their
    #    tokens into a page (a Go `html/template` block is html, not go). The later xml branch still
    #    takes pom.xml / CDI beans, whose element names are not HTML's.
    if b.startswith("<") and HTML.search(b):
        return "html"
    # 5. cmake before every other brace family: a build script is all call-form commands, and
    #    `project(...)`/`${CMAKE_*}` cannot appear in the languages it builds.
    if CMAKE.search(b):
        return "cmake"
    # 6. rust before the C family, because `std::` is Rust's path separator as much as C++'s
    #    (`use std::collections::HashMap`), and before js/ts, because `let mut` is Rust's alone
    #    while a bare `let` is shared with JS.
    if RUST.search(b):
        return "rust"
    # 7. C family before java AND python: `class Widget {` hits python's bare `\bclass\b` and
    #    `Widget w = make_widget();` hits java's typed-var form. Split on C++-only vocabulary.
    if C_FAMILY.search(b) or CPP_ONLY.search(b):
        return "cpp" if CPP_ONLY.search(b) else "c"
    # 8. go before python (python's bare `\bimport\b` would grab `import (`) and before ruby
    #    (`:=`/`func` are not Ruby, but Ruby's `nil` and Go's are the same token). A Makefile is
    #    checked first: it shares Go's `:=` assignment, and so do VHDL and Pascal — a block that
    #    looks like either of those is left to the branches below rather than claimed as Go.
    if MAKEFILE.search(b):
        return "makefile"
    if GO.search(b) and not VHDL_PASCAL.search(b):
        return "go"
    # 9. js/ts before ruby: an arrow function reads as a hashrocket to the ruby branch, and
    #    `export function` reads as a shell `export` to the bash branch.
    #    A lone `interface X {` decides nothing: Java writes it too, so it only tips the JS/TS
    #    choice once the block is already JS-family.
    is_ts = bool(TS_STRONG.search(b) or (TS_DECL.search(b) and JS.search(b)))
    if is_ts or JS.search(b):
        return "typescript" if is_ts else "javascript"
    # 10. ruby before python (shared `def`)
    if re.search(r"params\[:|=>|\bputs\b|\.each do\b", b):
        return "ruby"
    # 11. strong yaml / k8s / openapi markers only
    if re.search(
        r"^\s*(apiVersion|kind|openapi|swagger|paths|components|info|servers|security|schemas|metadata|spec):",
        b,
        re.M,
    ):
        return "yaml"
    # 12. dockerfile
    if re.search(r"^(FROM|RUN|CMD|ENTRYPOINT|COPY|WORKDIR)\s", b, re.M):
        return "dockerfile"
    # 13. xml (pom.xml / CDI beans / any well-formed tag pair) — before json
    if (
        re.match(r"\s*<\?xml", b)
        or re.search(
            r"^\s*</?(project|dependency|dependencies|groupId|artifactId|version|parent|plugin|plugins|build|configuration|profiles|beans|web-app|servlet|bean)\b",
            b,
            re.M,
        )
        or (re.match(r"\s*<[A-Za-z]", b) and re.search(r"</[A-Za-z][\w:.-]*>", b))
    ):
        return "xml"
    # 14. json: starts with { or [ and has "key": pairs (not a bare URL/placeholder)
    if re.match(r"\s*[\{\[]", b) and re.search(r'"\w+"\s*:', b):
        return "json"
    # 15. java / JVM — BEFORE python (Java `class`/`import` would otherwise hit the python branch).
    #    Precision-first: require a Java-specific signal, not just a semicolon (else Rust/C mislabel).
    if (
        re.search(r"^\s*@[A-Z]\w+", b, re.M)  # CapCamel annotation (@Inject, @ConfigProperty)
        or re.search(
            r"\b(public|private|protected)\s+(static\s+|final\s+|abstract\s+|synchronized\s+)*(class|interface|enum|record|void|[A-Z][\w<>\[\]]*)\b",
            b,
        )
        or re.search(r"\bimport\s+[\w.]+\s*;", b)  # import ...;  (semicolon = Java, not python)
        or re.search(r"\bpackage\s+[\w.]+\s*;", b)
        or re.search(
            r"\b(System\.out|System\.err|Objects\.hash|Optional\.|Collectors\.|Arrays\.asList|assertThat|assertEquals|assertTrue|orElseThrow)\b",
            b,
        )
        or re.search(
            r'\b[A-Z]\w+(<[\w,<>\[\] ]+>)?\s+\w+\s*=\s*(new\s+[A-Z]|[\w.]+\(|["\'])', b
        )  # typed var: Account a = new/method/"..."
        or re.search(r"\b[A-Z]\w+\.[A-Z][A-Z0-9_]{2,}\b", b)
    ):  # enum/constant access: AccountStatus.OVERDRAWN
        return "java"
    # 16. python
    if (
        re.search(r"\b(def|class|import|from|async\s+def|lambda)\b", b)
        or "BaseModel" in b
        or re.search(r"@\w+\.(get|post|put|delete|patch|middleware)", b)
    ):
        return "python"
    # 17. sql
    if re.search(
        r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE\s+TABLE|ALTER\s+TABLE)\b", b, re.I | re.M
    ):
        return "sql"
    # 18. shell: leading $/➜ prompt, a known CLI/build/k8s verb at line start, or an ENV=val-prefixed command
    if (
        re.search(r"(^|\n)\s*[\$➜]\s", b)
        or re.search(
            r"^\s*(uv|pip|pip3|curl|sudo|export|uvicorn|openssl|npm|npx|pnpm|yarn|git|docker|docker-compose|podman|pytest|python3?|"
            r"mvn|gradle|kubectl|helm|oc|minikube|make|cmake|ctest|ninja|meson|bazel|gcc|g\+\+|clang|clang\+\+|"
            r"rustup|rustc|tsc|node|deno|bun|conan|vcpkg|valgrind|gdb|"
            r"wget|apt|apt-get|yum|dnf|brew|chmod|mkdir|cd|tar|source|"
            r"quarkus|jbang|skaffold|kustomize|kubectx|kubens|\./mvnw|\./gradlew|\./)\s|"
            # `go`/`cargo` need a subcommand: bare `go func`/`cargo` tokens appear in source too.
            r"^\s*go\s+(build|test|run|get|mod|install|vet|fmt|doc|work|tool|generate|clean|list|env|version)\b|"
            r"^\s*cargo\s+(build|run|test|new|init|add|check|fmt|clippy|doc|publish|install|bench|update|tree)\b",
            b,
            re.M,
        )
        or re.match(r"[A-Z_]{2,}=\S+\s+\w", first)
    ):
        return "bash"
    # 19. ini: a real [section] header (alpha-started, not the [...] placeholder)
    if re.search(r"^\s*\[[A-Za-z][\w. ]*\]\s*$", b, re.M):
        return "ini"
    # 20. properties: dotted key=value (e.g. quarkus.http.port=8080, %prod.x=y)
    if (
        re.search(r"^\s*%?[\w-]+(\.[\w-]+)+\s*=", b, re.M)
        and "://" not in first
        and not re.search(r"^\s*(uv|pip|curl|export|git|docker|mvn|kubectl|helm)\b", b, re.M)
    ):
        return "properties"
    # 21. generic yaml: >=2 clean `key: value` lines, no URLs, not console "N:M" output
    kv = re.findall(r"^\s*[A-Za-z][\w-]*:\s+\S", b, re.M)
    if len(kv) >= 2 and "://" not in b and not re.match(r"\s*\d+:\d+", first):
        return "yaml"
    return "text"


def detect(cur_tag: str, body: str) -> tuple[str, str]:
    m = re.search(r"#\s*file:\s*\S+\.([A-Za-z0-9]+)", body)  # 1. file-ext hint
    if m and m.group(1).lower() in EXT:
        return EXT[m.group(1).lower()], "ext"
    # one alias table: explicit fence-tag aliases first, then the file-extension map (a fence tag is
    # very often just the extension: `py`, `rs`, `kt`, `js`, `proto`).
    canon_cur = CANON.get(cur_tag, EXT.get(cur_tag, cur_tag))
    if canon_cur not in GENERIC and canon_cur in VALID:  # 2. trust specific MinerU tag
        return canon_cur, "kept"
    return heuristic(body), "kw"  # 3. heuristic (4. -> text)


def retag(md: str) -> tuple[str, list[tuple[str, str, str, str]], collections.Counter[str]]:
    """Return (new_md, changes as (old, new, why, snippet), decision stats)."""
    changes: list[tuple[str, str, str, str]] = []
    stats: collections.Counter[str] = collections.Counter()

    def repl(blk: fences.Block) -> str | None:
        body = blk.body
        if blk.is_mermaid or not body.strip():
            return None
        info = blk.info.strip()
        if info.startswith("{"):
            # Pandoc/attribute syntax (```{.python .numberLines}): the language is fused into the
            # attribute list, so rewriting the first whitespace-separated token would emit a
            # malformed info string. Leave the block alone.
            return None
        raw_tag = info.split(None, 1)[0] if info else ""  # verbatim first token (case, punctuation)
        new, why = detect(blk.lang, body)
        stats[why] += 1
        if raw_tag == new:  # already canonical -> leave the block byte-identical
            return None
        changes.append((raw_tag or "<none>", new, why, body.strip().split("\n")[0][:55]))
        return blk.rebuild(lang=new)

    out = fences.transform(md, repl)
    return out, changes, stats
