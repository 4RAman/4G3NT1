import SwiftUI
import ButtonKit

/// The log, newest first. Read-only, and it stays that way: the event store is
/// the host's, and a phone that could edit history would be inventing a
/// direction the sync design does not have.
struct EventsView: View {
    @Environment(HostStore.self) private var store

    var body: some View {
        NavigationStack {
            List {
                ForEach(store.events) { row in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack {
                            Text(row.name.isEmpty ? row.kind : row.name)
                                .font(.body.weight(.medium))
                            Spacer()
                            Text(when(row))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text(detail(row))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 2)
                }
            }
            .navigationTitle("Log")
            .task { await store.loadEvents() }
            .refreshable { await store.loadEvents() }
            .overlay {
                if store.events.isEmpty {
                    ContentUnavailableView("Nothing logged yet",
                                           systemImage: "list.bullet.rectangle",
                                           description: Text("Presses and app "
                                            + "sessions show up here as they happen."))
                }
            }
        }
    }

    private func when(_ row: EventRow) -> String {
        guard let date = row.date else { return row.ts }
        return date.formatted(date: .omitted, time: .shortened)
    }

    private func detail(_ row: EventRow) -> String {
        var parts = [row.kind]
        if let mode = row.mode, mode != row.name { parts.append(mode) }
        if let value = row.value {
            parts.append(value == value.rounded() ? String(Int(value)) : String(format: "%g", value))
        }
        if let duration = row.durationS {
            parts.append(duration >= 60
                         ? "\(Int(duration / 60)) min"
                         : String(format: "%.0f s", duration))
        }
        return parts.joined(separator: " · ")
    }
}

#Preview {
    EventsView().environment(HostStore(client: PreviewHost()))
}
