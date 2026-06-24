#!/usr/bin/env python3
"""
Generate a synthetic engineering drawing for testing.

Creates a simple mechanical part drawing with:
- Front view (rectangle with a hole)
- Top view (simplified)
- Basic dimension labels
- Proper title block

Output: test_drawing.png (saved to storage/uploads/)
"""
import cv2
import numpy as np
from pathlib import Path

def create_test_drawing():
    # Canvas: A4 at 96 DPI (210x297 mm at 0.1 mm/px = 2100x2970 px, but let's do smaller)
    width, height = 1200, 1400
    canvas = np.ones((height, width, 3), dtype=np.uint8) * 255  # white background
    
    # Font
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    color_black = (0, 0, 0)
    thickness = 1
    
    # ---------- Title block (bottom right) ----------
    tb_x, tb_y = 900, 1050
    tb_w, tb_h = 280, 300
    cv2.rectangle(canvas, (tb_x, tb_y), (tb_x + tb_w, tb_y + tb_h), color_black, 1)
    cv2.putText(canvas, "PART NO: BRK-001", (tb_x + 10, tb_y + 25), font, 0.5, color_black, 1)
    cv2.putText(canvas, "MATERIAL: Al 6061", (tb_x + 10, tb_y + 50), font, 0.5, color_black, 1)
    cv2.putText(canvas, "SCALE: 1:2", (tb_x + 10, tb_y + 75), font, 0.5, color_black, 1)
    cv2.putText(canvas, "UNITS: mm", (tb_x + 10, tb_y + 100), font, 0.5, color_black, 1)
    # Projection symbol (simplified: small square to denote first-angle)
    cv2.rectangle(canvas, (tb_x + 10, tb_y + 130), (tb_x + 40, tb_y + 160), color_black, 1)
    cv2.putText(canvas, "1st Angle", (tb_x + 50, tb_y + 150), font, 0.4, color_black, 1)
    
    # ---------- FRONT VIEW ----------
    front_x, front_y = 150, 150
    front_w, front_h = 400, 350
    
    # Outline (rectangle)
    cv2.rectangle(canvas, (front_x, front_y), (front_x + front_w, front_y + front_h), color_black, 2)
    
    # Hole (circle in the center)
    hole_cx, hole_cy = front_x + front_w // 2, front_y + front_h // 2
    hole_r = 40
    cv2.circle(canvas, (hole_cx, hole_cy), hole_r, color_black, 2)
    
    # Centerlines for the hole
    cv2.line(canvas, (hole_cx - 60, hole_cy), (hole_cx + 60, hole_cy), color_black, 1)
    cv2.line(canvas, (hole_cx, hole_cy - 60), (hole_cx, hole_cy + 60), color_black, 1)
    
    # Dimension: height (left side)
    dim_x = front_x - 80
    cv2.line(canvas, (front_x - 10, front_y), (front_x - 10, front_y + front_h), color_black, 1)
    cv2.line(canvas, (front_x - 20, front_y), (front_x, front_y), color_black, 1)
    cv2.line(canvas, (front_x - 20, front_y + front_h), (front_x, front_y + front_h), color_black, 1)
    cv2.putText(canvas, "200", (dim_x - 40, front_y + front_h // 2), font, font_scale, color_black, thickness)
    
    # Dimension: width (bottom side)
    dim_y = front_y + front_h + 60
    cv2.line(canvas, (front_x, front_y + front_h + 10), (front_x + front_w, front_y + front_h + 10), color_black, 1)
    cv2.line(canvas, (front_x, front_y + front_h), (front_x, front_y + front_h + 20), color_black, 1)
    cv2.line(canvas, (front_x + front_w, front_y + front_h), (front_x + front_w, front_y + front_h + 20), color_black, 1)
    cv2.putText(canvas, "400", (front_x + front_w // 2 - 20, dim_y), font, font_scale, color_black, thickness)
    
    # Dimension: hole diameter (leader line style)
    cv2.line(canvas, (hole_cx + hole_r + 10, hole_cy), (hole_cx + 100, hole_cy - 40), color_black, 1)
    cv2.putText(canvas, "O 80", (hole_cx + 105, hole_cy - 30), font, font_scale, color_black, thickness)
    
    # Label
    cv2.putText(canvas, "FRONT VIEW", (front_x + 100, front_y - 20), font, 0.8, color_black, 2)
    
    # ---------- TOP VIEW ----------
    top_x, top_y = 700, 150
    top_w, top_h = 350, 280
    
    # Simplified: just the outline (ellipse for perspective)
    pts = np.array([
        [top_x, top_y + top_h // 2],
        [top_x + top_w // 2, top_y],
        [top_x + top_w, top_y + top_h // 2],
        [top_x + top_w // 2, top_y + top_h]
    ], np.int32)
    cv2.polylines(canvas, [pts], True, color_black, 2)
    
    # Hole circle (visible from top)
    hole_top_cx, hole_top_cy = top_x + top_w // 2, top_y + top_h // 2
    hole_top_r = 35
    cv2.circle(canvas, (hole_top_cx, hole_top_cy), hole_top_r, color_black, 2)
    
    # Centerlines
    cv2.line(canvas, (hole_top_cx - 50, hole_top_cy), (hole_top_cx + 50, hole_top_cy), color_black, 1)
    cv2.line(canvas, (hole_top_cx, hole_top_cy - 50), (hole_top_cx, hole_top_cy + 50), color_black, 1)
    
    # Label
    cv2.putText(canvas, "TOP VIEW", (top_x + 80, top_y - 20), font, 0.8, color_black, 2)
    
    # ---------- SIDE VIEW ----------
    side_x, side_y = 150, 600
    side_w, side_h = 350, 300
    
    # Outline (simpler, just a rectangle)
    cv2.rectangle(canvas, (side_x, side_y), (side_x + side_w, side_y + side_h), color_black, 2)
    
    # Hidden lines (dashed) for the hole depth
    for y_pos in range(side_y + side_h // 4, side_y + 3 * side_h // 4, 8):
        cv2.line(canvas, (side_x + side_w // 2 - 30, y_pos), (side_x + side_w // 2 + 30, y_pos), color_black, 1)
    
    # Dimension: depth
    dim_depth_y = side_y + side_h + 50
    cv2.line(canvas, (side_x, side_y + side_h + 10), (side_x + side_w, side_y + side_h + 10), color_black, 1)
    cv2.line(canvas, (side_x, side_y + side_h), (side_x, side_y + side_h + 20), color_black, 1)
    cv2.line(canvas, (side_x + side_w, side_y + side_h), (side_x + side_w, side_y + side_h + 20), color_black, 1)
    cv2.putText(canvas, "350", (side_x + side_w // 2 - 20, dim_depth_y), font, font_scale, color_black, thickness)
    
    # Label
    cv2.putText(canvas, "SIDE VIEW", (side_x + 80, side_y - 20), font, 0.8, color_black, 2)
    
    # ---------- INFO BLOCK ----------
    info_x, info_y = 150, 1050
    info_w = 700
    cv2.rectangle(canvas, (info_x, info_y), (info_x + info_w, info_y + 250), color_black, 1)
    cv2.putText(canvas, "NOTES:", (info_x + 10, info_y + 30), font, 0.7, color_black, 2)
    cv2.putText(canvas, "1. All dimensions in mm", (info_x + 10, info_y + 60), font, 0.5, color_black, 1)
    cv2.putText(canvas, "2. Tolerances: +/- 0.05 mm on critical dims", (info_x + 10, info_y + 85), font, 0.5, color_black, 1)
    cv2.putText(canvas, "3. Surface finish: Ra 1.6 um", (info_x + 10, info_y + 110), font, 0.5, color_black, 1)
    cv2.putText(canvas, "4. Hole depth: through", (info_x + 10, info_y + 135), font, 0.5, color_black, 1)
    
    # Save
    output_path = Path(__file__).parent.parent / "storage" / "uploads" / "test_drawing.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), canvas)
    print(f"✓ Test drawing created: {output_path}")
    print(f"  Dimensions: {width}x{height} pixels")
    print(f"  Contains: front view, top view, side view, dimension labels, title block")
    return output_path

if __name__ == "__main__":
    create_test_drawing()