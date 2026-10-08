# SuperTux

an attempt to make official super Tux WASM port run on github pages

### play da game
play da game at: https://cfels.github.io/stux-web/

### why this works?
beacuse is the game is split into smaller part's (32Mb) with a python script and then verified with another python script for game integirty

### upading game files

you'll need like python 3.x smth

```powershell
python scripts/update_gamefiles.py "C:\Downloads\SuperTux-WASM.zip"
```