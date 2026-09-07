import SwiftUI
import ButtonKit

/// The light, as it is right now.
///
/// The whole animation is `Look.render`, which is a pure function in ButtonKit
/// and therefore tested rather than watched. This view is a clock and a
/// circle; if the colour is wrong, the test is wrong.
struct LightView: View {
    var look: LedEffect?
    var diameter: CGFloat = 190

    private var isStill: Bool {
        Look.motion(for: look?.style ?? "solid") == .steady
    }

    var body: some View {
        Group {
            if isStill {
                // A steady look does not need a display-link redraw every
                // frame for the rest of the day.
                lamp(at: 0)
            } else {
                TimelineView(.animation) { timeline in
                    lamp(at: timeline.date.timeIntervalSinceReferenceDate)
                }
            }
        }
        .frame(width: diameter, height: diameter)
        .accessibilityLabel(description)
    }

    private func lamp(at time: Double) -> some View {
        let rgb = Look.render(look, at: time)
        let colour = Color(red: rgb.red, green: rgb.green, blue: rgb.blue)
        return ZStack {
            // The glow is what makes one pixel read as a light rather than a
            // circle of flat colour, and it is doing the same job the diffuser
            // does on the hardware.
            Circle()
                .fill(colour)
                .blur(radius: diameter * 0.18)
                .opacity(0.55)
                .scaleEffect(1.18)
            Circle()
                .fill(colour)
                .overlay(
                    Circle().strokeBorder(.white.opacity(0.10), lineWidth: 1)
                )
        }
    }

    private var description: String {
        guard let look else { return "The light is off" }
        return "The light is \(look.style)"
    }
}

#Preview {
    VStack(spacing: 24) {
        LightView(look: LedEffect(style: "breathe", color: "#1e40ff", periodS: 4),
                  diameter: 120)
        LightView(look: LedEffect(style: "alternate", color: "#ff0000",
                                  color2: "#ffffff", periodS: 0.6), diameter: 120)
        LightView(look: nil, diameter: 120)
    }
    .padding()
}
