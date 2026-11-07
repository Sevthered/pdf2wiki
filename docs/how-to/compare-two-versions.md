# Compare the output of two versions

`pdf2wiki compare` compares the Markdown files of two folders. Use it to check that a new pdf2wiki
version gives the same chapter files as an older version. Use it also to see what a step such as
`--links` changes. The command only reads the two folders. It does not run `phase5` and does not
write a file.

## Compare two folders

```bash
pdf2wiki compare ~/gate/old ~/gate/new
```

Each folder can hold the chapter files of one book, or a folder for each book. The command pairs the
files by their path in the folder. It compares the text of Markdown files only: `.md` and
`.markdown`, in uppercase or lowercase. It pairs the other files too, such as images and `.log`
files, but it does not read them. The `.log` files of two runs are always different.

Before the compare, the command removes the frontmatter `source:` line from each file. `phase5`
writes the path of the input file there, and this path is different in each run. A line in the body
that starts with `source:` is not removed.

The output shows one line for each file that is not the same, then the totals:

```
compare /home/me/gate/old -> /home/me/gate/new (frontmatter keys ignored: source)
different    my-book/chapters/03-intro.md  +2 -1
only in NEW  my-book/chapters/04-setup.md
28 compared: 27 same, 1 different. 0 only in OLD, 1 only in NEW. 1 other file in both folders, not read.
```

The exit code is the same as the exit code of `diff`:

- `0`: all Markdown files are the same, and no file of any type is in one folder only.
- `1`: a Markdown file is different, or a file is in one folder only. For example, an image that
  the new version does not write gives exit code `1`.
- `2`: an error. For example, a folder does not exist, or OLD and NEW are the same folder.

## See the changes

To see the first lines of the unified diff of each different file, add `--diff N`:

```bash
pdf2wiki compare ~/gate/old ~/gate/new --diff 20
```

The line numbers in a diff are the line numbers of the real files. A hunk can include an ignored
line in its range, but the diff does not show that line. A carriage return shows as `␍` at the
end of the line.

To ignore more frontmatter keys, give `--ignore-key` for each key. The keys you give replace the
default `source`, so give `source` again if you want it ignored:

```bash
pdf2wiki compare ~/gate/old ~/gate/new --ignore-key source --ignore-key updated
```

To compare all frontmatter keys, also `source`, add `--no-ignore`. You cannot use `--no-ignore`
and `--ignore-key` together.

To use the report in a script, add `--json`. The JSON report also lists the files that are the same.

## Do the release check

This procedure compares the output of an old release with the output of the installed version. It
uses one converted book, `my-book`.

1. Make the work folders:

   ```bash
   mkdir -p ~/gate/v-old ~/gate/in-old ~/gate/in-new ~/gate/old ~/gate/new
   ```

2. Get the source code of the old release from the pdf2wiki repository:

   ```bash
   git -C ~/src/pdf2wiki archive v0.3.0 src | tar -x -C ~/gate/v-old
   ```

3. Copy the converted book into the `in-old` folder and into the `in-new` folder. Do not run
   `phase5 --apply` on a book that you want to keep. Each run gets its own copy, because a release
   before v0.2.10 changed the source `.md` with `--apply`:

   ```bash
   cp -R ~/pdf2wiki/out/my-book ~/gate/in-old/
   cp -R ~/pdf2wiki/out/my-book ~/gate/in-new/
   ```

4. Run `phase5` from the old release. Use a Python that has the dependencies of pdf2wiki installed:

   ```bash
   cd ~/gate
   PYTHONPATH=~/gate/v-old/src python -c 'import sys;from pdf2wiki.cli import main;sys.exit(main())' \
     phase5 in-old/my-book/my-book.md --book my-book --out old/my-book --apply
   ```

5. Run `phase5` from the installed version:

   ```bash
   pdf2wiki phase5 in-new/my-book/my-book.md --book my-book --out new/my-book --apply
   ```

6. Compare the two folders:

   ```bash
   pdf2wiki compare old new
   ```

Exit code `0` means that the new version gives the same chapter files. For more books, do steps 3 to
5 for each book, then do step 6 one time.

`PYTHONPATH` puts the old source code before the installed package, so Python imports the old
version. Before you run step 4, make sure that `--version` shows the old version number.

## Symlinks

The command follows a symlink to a file. It does not go into a symlink to a folder, so a link back to
a parent folder cannot cause a loop. It pairs a symlink to a folder like a file that it does not
read. A Markdown symlink to a file that does not exist stops the command with exit code `2`.

## Line ends and encoding

A file with CRLF line ends is different from the same file with LF line ends. The output then says
`(line ends only)`. A file that is not valid UTF-8 is compared as bytes. The command then says if the
file is the same or different, but it does not count lines or show a diff.

See the [CLI reference](../reference/cli.md#compare) for each flag.
