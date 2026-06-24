# Frontend (planned — Step 4)

React + Vite app with an HTML5 canvas for the lasso/crop UI (Slice A) and an
SVG overlay for inspecting extracted geometry (Slice B).

Not implemented yet. Scaffold this with:

```bash
npm create vite@latest . -- --template react
```

Key pieces to build:
- Canvas that loads the uploaded drawing and captures a freehand lasso path.
- Convert canvas points back to true image pixels before POSTing (track the
  canvas-to-image scale factor).
- Label dropdown (front / top / side / section / detail / iso / info) + notes.
- Saved-crops list that reloads from `GET /drawings/{id}/views`.
- Geometry overlay toggle for the CV extraction result.
