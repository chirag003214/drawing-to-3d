import { useEffect, useRef, useState } from 'react'
import { uploadDrawing, createView, listViews, getView, cropUrl, extractView } from './api'

const LABELS = ['front', 'top', 'side', 'section', 'detail', 'iso', 'info']
const LAYER_COLORS = {
  object: '#1f6feb',
  dimension: '#d29922',
  centerline: '#8957e5',
  hidden: '#6e7681',
  unknown: '#bbbbbb',
}

export default function App() {
  const [drawing, setDrawing] = useState(null) // {id, width, height}
  const [image, setImage] = useState(null) // HTMLImageElement
  const [views, setViews] = useState([])
  const [selectedView, setSelectedView] = useState(null) // full ViewDetailOut
  const [label, setLabel] = useState('front')
  const [notes, setNotes] = useState('')
  const [pxPerMm, setPxPerMm] = useState('')
  const [points, setPoints] = useState([]) // lasso points in canvas-display coords
  const [drawing_, setDrawingFlag] = useState(false)
  const [showOverlay, setShowOverlay] = useState(true)
  const [showRawIr, setShowRawIr] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [error, setError] = useState(null)

  const canvasRef = useRef(null)
  const containerRef = useRef(null)
  const CANVAS_MAX_W = 800

  const canvasDims = image
    ? (() => {
        const scale = Math.min(1, CANVAS_MAX_W / image.width)
        return { w: image.width * scale, h: image.height * scale }
      })()
    : { w: 0, h: 0 }

  useEffect(() => {
    redraw()
  }, [image, points, canvasDims.w, canvasDims.h])

  function redraw() {
    const canvas = canvasRef.current
    if (!canvas || !image) return
    canvas.width = canvasDims.w
    canvas.height = canvasDims.h
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height)
    if (points.length > 0) {
      ctx.beginPath()
      ctx.moveTo(points[0].x, points[0].y)
      for (const p of points.slice(1)) ctx.lineTo(p.x, p.y)
      ctx.strokeStyle = '#ff3b30'
      ctx.lineWidth = 2
      ctx.stroke()
      if (points.length > 2) {
        ctx.lineTo(points[0].x, points[0].y)
        ctx.fillStyle = 'rgba(255,59,48,0.15)'
        ctx.fill()
      }
    }
  }

  async function handleUpload(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setError(null)
    try {
      const d = await uploadDrawing(file)
      setDrawing(d)
      setSelectedView(null)
      setPoints([])
      const img = new Image()
      img.onload = () => setImage(img)
      img.src = URL.createObjectURL(file)
      const vs = await listViews(d.id)
      setViews(vs)
    } catch (err) {
      setError(String(err))
    }
  }

  function canvasPointFromEvent(e) {
    const canvas = canvasRef.current
    const rect = canvas.getBoundingClientRect()
    const clientX = e.touches ? e.touches[0].clientX : e.clientX
    const clientY = e.touches ? e.touches[0].clientY : e.clientY
    return { x: clientX - rect.left, y: clientY - rect.top }
  }

  function onPointerDown(e) {
    if (!image) return
    setDrawingFlag(true)
    setPoints([canvasPointFromEvent(e)])
  }

  function onPointerMove(e) {
    if (!drawing_) return
    setPoints((prev) => [...prev, canvasPointFromEvent(e)])
  }

  function onPointerUp() {
    setDrawingFlag(false)
  }

  async function handleSaveView() {
    if (!drawing || points.length < 3) {
      setError('Lasso at least 3 points before saving a view.')
      return
    }
    setError(null)
    try {
      const polygon = points.map((p) => [p.x, p.y])
      const view = await createView(drawing.id, {
        polygon,
        label,
        notes: notes || null,
        px_per_mm: pxPerMm ? parseFloat(pxPerMm) : null,
        canvas_w: canvasDims.w,
        canvas_h: canvasDims.h,
      })
      setPoints([])
      const vs = await listViews(drawing.id)
      setViews(vs)
      await selectView(view.id)
    } catch (err) {
      setError(String(err))
    }
  }

  async function selectView(viewId) {
    setError(null)
    try {
      const v = await getView(viewId)
      setSelectedView(v)
    } catch (err) {
      setError(String(err))
    }
  }

  async function handleExtract() {
    if (!selectedView) return
    setExtracting(true)
    setError(null)
    try {
      await extractView(selectedView.id)
      await selectView(selectedView.id)
    } catch (err) {
      setError(String(err))
    } finally {
      setExtracting(false)
    }
  }

  return (
    <div className="app">
      <h1>Drawing → 3D IR Inspector</h1>
      <p className="subtitle">
        Upload a drawing, lasso a view, label it, then run CV extraction on the saved crop.
      </p>

      {error && <div className="error">{error}</div>}

      <div className="layout">
        <div className="left-pane">
          <section className="panel">
            <h2>1. Upload</h2>
            <input type="file" accept="image/*" onChange={handleUpload} />
          </section>

          {image && (
            <section className="panel">
              <h2>2. Lasso a view</h2>
              <div ref={containerRef}>
                <canvas
                  ref={canvasRef}
                  className="lasso-canvas"
                  onMouseDown={onPointerDown}
                  onMouseMove={onPointerMove}
                  onMouseUp={onPointerUp}
                  onMouseLeave={onPointerUp}
                  onTouchStart={onPointerDown}
                  onTouchMove={onPointerMove}
                  onTouchEnd={onPointerUp}
                />
              </div>
              <div className="form-row">
                <label>
                  Label
                  <select value={label} onChange={(e) => setLabel(e.target.value)}>
                    {LABELS.map((l) => (
                      <option key={l} value={l}>{l}</option>
                    ))}
                  </select>
                </label>
                <label>
                  px/mm (optional)
                  <input
                    type="number"
                    step="0.01"
                    value={pxPerMm}
                    onChange={(e) => setPxPerMm(e.target.value)}
                  />
                </label>
              </div>
              <label className="notes-label">
                Notes
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
              </label>
              <div className="button-row">
                <button onClick={handleSaveView} disabled={points.length < 3}>
                  Save view ({points.length} pts)
                </button>
                <button onClick={() => setPoints([])} disabled={points.length === 0}>
                  Clear lasso
                </button>
              </div>
            </section>
          )}

          {drawing && (
            <section className="panel">
              <h2>3. Saved views</h2>
              {views.length === 0 && <p className="muted">None yet.</p>}
              <ul className="view-list">
                {views.map((v) => (
                  <li key={v.id}>
                    <button
                      className={selectedView?.id === v.id ? 'view-btn active' : 'view-btn'}
                      onClick={() => selectView(v.id)}
                    >
                      <img src={cropUrl(v.id)} alt={v.label} className="thumb" />
                      <span>{v.label}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <div className="right-pane">
          {selectedView && (
            <section className="panel">
              <h2>4. Extraction</h2>
              <div className="button-row">
                <button onClick={handleExtract} disabled={extracting}>
                  {extracting ? 'Extracting…' : 'Run CV extraction'}
                </button>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={showOverlay}
                    onChange={(e) => setShowOverlay(e.target.checked)}
                  />
                  Show geometry overlay
                </label>
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={showRawIr}
                    onChange={(e) => setShowRawIr(e.target.checked)}
                  />
                  View raw IR
                </label>
              </div>

              <div className="overlay-stage">
                <img src={cropUrl(selectedView.id)} alt="crop" className="crop-img" />
                {showOverlay && (
                  <svg
                    className="overlay-svg"
                    viewBox={`0 0 ${selectedView.crop_w || 1} ${selectedView.crop_h || 1}`}
                  >
                    {selectedView.primitives.map((p) => {
                      const color = LAYER_COLORS[p.layer] || LAYER_COLORS.unknown
                      const opacity = p.confidence < 0.5 ? 0.4 : 0.9
                      if (p.kind === 'line') {
                        const g = p.geom
                        return (
                          <line
                            key={p.id}
                            x1={g.x1} y1={g.y1} x2={g.x2} y2={g.y2}
                            stroke={color} strokeWidth={2} opacity={opacity}
                          />
                        )
                      }
                      const g = p.geom
                      return (
                        <circle
                          key={p.id}
                          cx={g.cx} cy={g.cy} r={g.r}
                          fill="none" stroke={color} strokeWidth={2} opacity={opacity}
                          strokeDasharray={p.kind === 'arc' ? '4,3' : 'none'}
                        />
                      )
                    })}
                  </svg>
                )}
              </div>

              <div className="legend">
                {Object.entries(LAYER_COLORS).map(([k, c]) => (
                  <span key={k} className="legend-item">
                    <span className="swatch" style={{ background: c }} /> {k}
                  </span>
                ))}
              </div>

              <p className="muted">
                {selectedView.primitives.length} primitives, {selectedView.dimensions.length} dimensions.
                Dimension→geometry links are an unconfirmed nearest-primitive heuristic, not asserted truth.
              </p>

              {showRawIr && (
                <pre className="raw-ir">{JSON.stringify(selectedView, null, 2)}</pre>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  )
}
