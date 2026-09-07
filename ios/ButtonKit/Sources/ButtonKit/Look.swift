import Foundation

/// A colour as the config writes it, taken apart far enough to draw.
public struct RGB: Sendable, Equatable {
    public var red: Double
    public var green: Double
    public var blue: Double

    public init(red: Double, green: Double, blue: Double) {
        self.red = red
        self.green = green
        self.blue = blue
    }

    /// "#ff8800", "ff8800", "#f80". Nil for anything else, and the caller
    /// draws its own fallback rather than being handed a wrong colour
    /// confidently.
    public init?(hex: String?) {
        guard var text = hex?.trimmingCharacters(in: .whitespaces) else { return nil }
        if text.hasPrefix("#") { text.removeFirst() }
        let digits = Array(text.lowercased())
        guard !digits.isEmpty, digits.allSatisfy({ $0.isHexDigit }) else { return nil }
        let channels: [String]
        switch digits.count {
        case 3: channels = digits.map { String(repeating: $0, count: 2) }
        case 6: channels = stride(from: 0, to: 6, by: 2).map { String(digits[$0...$0 + 1]) }
        default: return nil
        }
        let values = channels.compactMap { Int($0, radix: 16) }
        guard values.count == 3 else { return nil }
        red = Double(values[0]) / 255
        green = Double(values[1]) / 255
        blue = Double(values[2]) / 255
    }

    /// The brightest channel. `rainbow` reads its brightness out of the
    /// colour this way on the device (CAP_RAINBOW_LEVEL), so the phone reads
    /// it the same way rather than inventing a second convention.
    public var level: Double { max(red, max(green, blue)) }

    public func scaled(_ factor: Double) -> RGB {
        RGB(red: red * factor, green: green * factor, blue: blue * factor)
    }

    public func mixed(with other: RGB, amount: Double) -> RGB {
        RGB(red: red + (other.red - red) * amount,
            green: green + (other.green - green) * amount,
            blue: blue + (other.blue - blue) * amount)
    }

    /// Hue, saturation and value in 0...1, the way `rainbow` generates them.
    public static func hsv(hue: Double, saturation: Double, value: Double) -> RGB {
        let h = (hue - hue.rounded(.down)) * 6
        let sector = Int(h)
        let f = h - Double(sector)
        let p = value * (1 - saturation)
        let q = value * (1 - saturation * f)
        let t = value * (1 - saturation * (1 - f))
        switch sector {
        case 0: return RGB(red: value, green: t, blue: p)
        case 1: return RGB(red: q, green: value, blue: p)
        case 2: return RGB(red: p, green: value, blue: t)
        case 3: return RGB(red: p, green: q, blue: value)
        case 4: return RGB(red: t, green: p, blue: value)
        default: return RGB(red: value, green: p, blue: q)
        }
    }

    public static let unlit = RGB(red: 0.11, green: 0.11, blue: 0.13)
    public static let off = RGB(red: 0, green: 0, blue: 0)
}

/// How a look moves.
///
/// Not a mirror of `STYLE_USES_COLOR` and friends: those exist so the *editor*
/// can hide fields that would do nothing, and the phone is not editing. This
/// is only "what should the light do", and a style this file has never seen
/// falls to `.steady` - a colour sitting still is a wrong animation, never a
/// blank screen.
public enum LookMotion: Sendable, Equatable {
    case steady     // solid
    case pulse      // breathe - smooth, one colour
    case blink      // flash - hard on/off
    case swap       // alternate - hard, two colours
    case crossfade  // fade - smooth, two colours
    case spectrum   // rainbow - generated hues
}

public enum Look {

    public static func motion(for style: String) -> LookMotion {
        switch style {
        case "breathe": return .pulse
        case "flash": return .blink
        case "alternate": return .swap
        case "fade": return .crossfade
        case "rainbow": return .spectrum
        default: return .steady
        }
    }

    /// A look taken apart: two colours, how it moves, and how long a cycle is.
    ///
    /// **No second flash floor here, deliberately.** `config.flash_safe` has
    /// already floored anything that reaches the wire, and every look the app
    /// sees came off `/api/status` - so these are values the host has already
    /// clamped. A floor in a fourth place is a floor with a fourth chance to
    /// drift; see CLAUDE.md's "The flash floor has one gate".
    public static func swatch(_ effect: LedEffect?) -> (base: RGB, alternate: RGB,
                                                        motion: LookMotion,
                                                        periodS: Double) {
        guard let effect else { return (.unlit, .unlit, .steady, 1) }
        let movement = motion(for: effect.style)
        let base = RGB(hex: effect.color) ?? .unlit
        let alternate = RGB(hex: effect.color2) ?? .off
        // A period of zero divides by nothing in every animation below; a look
        // that did not say gets one second rather than a crash.
        let period = (effect.periodS ?? 0) > 0 ? effect.periodS! : 1
        return (base, alternate, movement, period)
    }

    /// What colour the light is at a moment in time.
    ///
    /// Pure, and that is the point: the phone's light is a `TimelineView` over
    /// this function, so what the swatch shows can be checked in a test rather
    /// than watched. `time` is seconds on any monotonic scale - only the
    /// difference between calls matters.
    public static func render(_ effect: LedEffect?, at time: Double) -> RGB {
        guard let effect else { return .unlit }
        let (base, alternate, movement, period) = swatch(effect)
        var phase = time / period
        phase -= phase.rounded(.down)
        let wave = 0.5 - 0.5 * cos(2 * Double.pi * phase)  // 0 at the ends, 1 in the middle

        switch movement {
        case .steady:
            return base
        case .pulse:
            // Never all the way off: a breathe that hits black reads as a
            // flash, which is a different thing with a different safety rule.
            return base.scaled(0.15 + 0.85 * wave)
        case .blink:
            return phase < 0.5 ? base : .off
        case .swap:
            return phase < 0.5 ? base : alternate
        case .crossfade:
            return base.mixed(with: alternate, amount: wave)
        case .spectrum:
            // Level and saturation live in the two colour fields, exactly as
            // the device reads them - see CAP_RAINBOW_LEVEL / CAP_RAINBOW_SAT.
            let value = RGB(hex: effect.color)?.level ?? 1
            let saturation = RGB(hex: effect.color2)?.level ?? 1
            return RGB.hsv(hue: phase, saturation: saturation, value: value)
        }
    }
}
