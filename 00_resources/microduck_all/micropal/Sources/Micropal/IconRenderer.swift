import AppKit

/// Offscreen rendering of the duck to PNG. Reuses the exact layer tree the app
/// draws with, so the icon and any verification renders always match the pet.
enum IconRenderer {
    /// Renders the duck (transparent background) or the app icon (pastel
    /// rounded-rect background) to a PNG file. Returns false on failure.
    @discardableResult
    static func render(to path: String, pixels: Int, colorway: Int, iconBackground: Bool,
                       style: DuckStyle = .classic) -> Bool {
        let palette: DuckPalette
        if colorway >= 0 && colorway < DuckPalette.presets.count {
            palette = DuckPalette.presets[colorway].palette
        } else {
            palette = DuckPalette.presets[0].palette
        }

        let viewSize = DuckLayerView.viewSize(scale: 1)
        let view = DuckLayerView(frame: NSRect(origin: .zero, size: viewSize))
        view.apply(style: style)
        view.apply(palette: palette)
        view.apply(pose: .neutral, facing: 1)
        view.layoutSubtreeIfNeeded()
        CATransaction.flush()

        guard let rep = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .calibratedRGB, bytesPerRow: 0, bitsPerPixel: 0),
            let nsCtx = NSGraphicsContext(bitmapImageRep: rep)
        else { return false }

        let ctx = nsCtx.cgContext
        let px = CGFloat(pixels)

        if iconBackground {
            let inset = px * 0.06
            let bg = CGRect(x: inset, y: inset, width: px - 2 * inset, height: px - 2 * inset)
            ctx.setFillColor(NSColor(hex: "#F6EFDF").cgColor)
            ctx.addPath(CGPath(roundedRect: bg, cornerWidth: px * 0.2, cornerHeight: px * 0.2,
                               transform: nil))
            ctx.fillPath()
        }

        // The duck occupies a 100x120 design box centered at the view's bottom.
        let duckRect = CGRect(x: viewSize.width / 2 - 50,
                              y: DuckLayerView.bottomMarginDesign,
                              width: 100, height: 120)
        let fit = px * (iconBackground ? 0.66 : 0.9) / duckRect.height
        ctx.saveGState()
        ctx.translateBy(x: px / 2 - duckRect.midX * fit, y: px / 2 - duckRect.midY * fit)
        ctx.scaleBy(x: fit, y: fit)
        view.layer.map { $0.render(in: ctx) }
        ctx.restoreGState()

        guard let data = rep.representation(using: .png, properties: [:]) else { return false }
        do {
            try data.write(to: URL(fileURLWithPath: path))
            return true
        } catch {
            fputs("render failed: \(error)\n", stderr)
            return false
        }
    }
}
