# External tools

Place `planetiler.jar` here (required by depot MapGen).

Download from: https://github.com/onthegomap/planetiler/releases

```bash
cd "$(dirname "$0")"
curl -L -o planetiler.jar \
  "https://github.com/onthegomap/planetiler/releases/latest/download/planetiler.jar"
chmod +x planetiler.jar   # depot checks executability via which()
```

Depot resolves it with `shutil.which("planetiler.jar")`, so add this directory to your PATH before running `IST.py`:

```bash
export PATH="$PWD/tools:$PATH"
```
