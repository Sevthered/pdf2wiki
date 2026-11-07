# Export and check the code listings of a book

Use `pdf2wiki listings` to find the code of a converted book. The command can write each code block
to its own file. It can also find blocks that do not parse, such as code with a lost indent or a
wrong language tag. The command never changes the chapter files.

You need a folder with the chapter files of one book, as `phase5` writes them.

## 1. Count the code blocks

```bash
pdf2wiki listings ~/books/my-book/chapters
```

The command prints the number of code blocks for each language and for each chapter file. It also
prints how many blocks have a "Listing X.Y" caption.

## 2. Check the code blocks

```bash
pdf2wiki listings ~/books/my-book/chapters --check
```

The command parses each block in a known language and gives each block one class:

- `ok`: the block parses.
- `fragment`: the block is a part of a program, such as a REPL session or the end of a function.
  Books show code in parts, so this class is normal.
- `wrong-language?`: the block looks like a different language. Examine the fence tag.
- `error`: the block does not parse. Examine the block in the chapter file and in the PDF.

The command lists each `error` and `wrong-language?` block with its file and line:

```
  07-chapter-4.md:120 python wrong-language?: parses as go
  08-chapter-5.md:88 python error: invalid character '’' (U+2019) (line 2)
```

The line after the file name is the line of the opening fence. The line in the message counts from
the first line of the block.

`--check` always exits with code `0`. To use the result in a script, add `--json` and read the
`findings` list.

## 3. Export the code blocks

```bash
pdf2wiki listings ~/books/my-book/chapters --out ~/books/my-book/listings
```

The output folder must not exist or must be empty. The command writes one folder for each chapter
file and one file for each block. A block with a "Listing 4.1" caption gets a name such as
`02-listing-4-1.java`. The command also writes `index.json`, which connects each file to its chapter
file and line.

Add `--check` to put the check result of each block in `index.json`.

## Related

- [`listings` reference](../reference/cli.md#listings): all options and classes.
- [Exported listings](../reference/output-layout.md#exported-listings): the file names and the
  `index.json` keys.
