# json interactive stream editor

A tool inspired by [Ultimate Plumber](https://github.com/akavel/up) that uses [jq](https://stedolan.github.io/jq) to process JSON and show you the results instantly, to enable greater interactivity.

[![asciicast](https://asciinema.org/a/313423.svg)](https://asciinema.org/a/313423)

[A manual for jq can be found here.](https://stedolan.github.io/jq/manual)

## Download & Install

```bash
sudo apt install jq  # <-- Install the jq tool, on MacOS install using `brew install jq`
pip3 install jqed
```

## Usage / Examples
```sh
cat some_file.json | jqed
ip --json link | jqed
```
