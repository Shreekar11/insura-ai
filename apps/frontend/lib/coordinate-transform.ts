import { BoundingBox } from "@/types/citation";

export interface ViewerBox {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Transform PDF coordinates (bottom-left origin, PDF points) to viewer coordinates (top-left origin, pixels)
 *
 * @param bbox - Bounding box in PDF coordinates (bottom-left origin)
 * @param pageHeight - Page height in PDF points
 * @param scale - Current viewer scale/zoom level
 * @returns ViewerBox in pixel coordinates (top-left origin)
 */
export function pdfToViewerCoordinates(
  bbox: BoundingBox,
  pageHeight: number,
  scale: number = 1
): ViewerBox {
  return {
    left: bbox.x0 * scale,
    top: (pageHeight - bbox.y1) * scale, // Flip Y-axis
    width: (bbox.x1 - bbox.x0) * scale,
    height: (bbox.y1 - bbox.y0) * scale,
  };
}

/**
 * Transform multiple bounding boxes for a page
 */
export function transformPageBoxes(
  boxes: BoundingBox[],
  pageHeight: number,
  scale: number = 1
): ViewerBox[] {
  return boxes.map((box) => pdfToViewerCoordinates(box, pageHeight, scale));
}
