# Brand icon

`scene.html` renders the 3D icon with three.js; `serve.py` serves it and stores the canvas PNG; `finish.py` crops it
and builds `icon`, `logo` and `dark_logo` (1x and @2x) for `custom_components/malarenergi_powerhub/brand/`.

```bash
cd tools/brand && mkdir -p out && python3 serve.py .          # serves http://127.0.0.1:8765
# open http://127.0.0.1:8765/scene.html?size=2048 in a browser, then in its devtools console:
#   await save("icon_raw.png")                                 # writes out/icon_raw.png
python3 finish.py out/icon_raw.png ../../custom_components/malarenergi_powerhub/brand
cp ../../custom_components/malarenergi_powerhub/brand/icon.png ../../icon.png
```

`finish.py` needs Pillow and the DejaVu Sans Bold font (`/usr/share/fonts/truetype/dejavu/`).
