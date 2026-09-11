import SwiftUI

struct SettingsView: View {
    @ObservedObject var store: SettingsStore
    @State private var launchAtLogin = false
    @State private var launchAtLoginError: String?

    var body: some View {
        Form {
            Section("Style") {
                Picker("Design", selection: $store.styleIndex) {
                    ForEach(DuckStyle.allCases, id: \.rawValue) { style in
                        Text(style.displayName).tag(style.rawValue)
                    }
                }
                .pickerStyle(.segmented)
            }

            Section("Colorway") {
                HStack(spacing: 12) {
                    ForEach(Array(DuckPalette.presets.enumerated()), id: \.offset) { index, preset in
                        swatch(for: preset, index: index)
                    }
                    Button {
                        store.startCustomizing()
                    } label: {
                        VStack(spacing: 4) {
                            Image(systemName: "paintpalette")
                                .frame(width: 28, height: 28)
                            Text("Custom").font(.caption2)
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(4)
                    .background(selectionBackground(selected: store.colorwayIndex == -1))
                }
                if store.colorwayIndex == -1 {
                    colorRow("Shell", $store.customShell)
                    colorRow("Beak & trim", $store.customAccent)
                    colorRow("Eye ring", $store.customEyeRing)
                    colorRow("Feet", $store.customFeetTop)
                    colorRow("Soles", $store.customFeetSole)
                }
            }

            Section("Size & energy") {
                HStack {
                    Text("Size")
                    Slider(value: $store.sizeScale, in: 0.5...2.0)
                    Text(String(format: "%.0f%%", store.sizeScale * 100))
                        .monospacedDigit()
                        .frame(width: 46, alignment: .trailing)
                }
                HStack {
                    Text("Activity")
                    Slider(value: $store.activity, in: 0.25...3.0)
                    Text(String(format: "%.1fx", store.activity))
                        .monospacedDigit()
                        .frame(width: 46, alignment: .trailing)
                }
            }

            Section("Behaviors") {
                Toggle("React to clicks", isOn: $store.clickEnabled)
                Toggle("Pick up & drop with the mouse", isOn: $store.dragEnabled)
                Toggle("Watch the cursor", isOn: $store.cursorEnabled)
                Toggle("Kick", isOn: $store.kickEnabled)
                Toggle("Peck at the ground", isOn: $store.peckEnabled)
                Toggle("Fall over (and get back up)", isOn: $store.fallEnabled)
                Toggle("Roller skate", isOn: $store.skateEnabled)
                Toggle("Sit down", isOn: $store.sitEnabled)
            }

            Section {
                Toggle("Launch at login", isOn: $launchAtLogin)
                    .disabled(!SettingsStore.canManageLaunchAtLogin)
                    .onChange(of: launchAtLogin) { newValue in
                        guard newValue != store.launchAtLoginEnabled else { return }
                        do {
                            try store.setLaunchAtLogin(newValue)
                            launchAtLoginError = nil
                        } catch {
                            launchAtLogin = store.launchAtLoginEnabled
                            launchAtLoginError = error.localizedDescription
                        }
                    }
                if !SettingsStore.canManageLaunchAtLogin {
                    Text("Available when running from the built app bundle.")
                        .font(.caption).foregroundStyle(.secondary)
                }
                if let launchAtLoginError {
                    Text(launchAtLoginError).font(.caption).foregroundStyle(.red)
                }
            } footer: {
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Micropal — an homage to [Microduck](https://pollen-robotics.com/microduck/) by [Pollen Robotics](https://pollen-robotics.com/)")
                        Text("Created by [@ATMartin](https://github.com/ATMartin)")
                    }
                    .font(.caption).foregroundStyle(.secondary)
                    Spacer()
                    Button("Quit") { NSApp.terminate(nil) }
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 380)
        .fixedSize(horizontal: false, vertical: true)
        .onAppear { launchAtLogin = store.launchAtLoginEnabled }
    }

    private func swatch(for preset: DuckPalette.Preset, index: Int) -> some View {
        Button {
            store.colorwayIndex = index
        } label: {
            VStack(spacing: 4) {
                ZStack {
                    Circle().fill(Color(nsColor: preset.palette.shell))
                        .frame(width: 28, height: 28)
                    Circle().fill(Color(nsColor: preset.palette.accent))
                        .frame(width: 12, height: 12)
                        .offset(x: 6, y: 6)
                }
                Text(preset.name).font(.caption2)
            }
        }
        .buttonStyle(.plain)
        .padding(4)
        .background(selectionBackground(selected: store.colorwayIndex == index))
    }

    private func selectionBackground(selected: Bool) -> some View {
        RoundedRectangle(cornerRadius: 8)
            .stroke(selected ? Color.accentColor : .clear, lineWidth: 2)
    }

    private func colorRow(_ label: String, _ hex: Binding<String>) -> some View {
        ColorPicker(label, selection: Binding<Color>(
            get: { Color(nsColor: NSColor(hex: hex.wrappedValue)) },
            set: { hex.wrappedValue = NSColor($0).hexString }
        ), supportsOpacity: false)
    }
}
