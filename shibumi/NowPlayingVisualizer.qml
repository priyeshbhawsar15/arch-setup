pragma ComponentBehavior: Bound

import QtQuick
import qs.Commons as Commons

// Compact 4-bar decorative visualizer shown to the right of the clock/notch
// content while a track is actively playing. Bars idle flat when paused or
// no player is active.
Item {
  id: root

  required property var bar
  readonly property var mediaService: bar && bar.shell
    && typeof bar.shell.firstPartyServiceFor === "function"
    ? bar.shell.firstPartyServiceFor("omarchy.media") : null
  readonly property var activePlayer: mediaService ? mediaService.activePlayer : null
  readonly property bool active: !!(activePlayer
    && (activePlayer.trackTitle || activePlayer.trackArtist))
  readonly property bool playing: active && activePlayer.isPlaying === true

  readonly property color themeAccent: (bar && bar.urgent)
    ? bar.urgent
    : (bar && bar.visualTokens && bar.visualTokens.seal
      ? bar.visualTokens.seal : Commons.Color.bar.active)

  visible: active
  implicitWidth: active ? 18 + Commons.Style.space(6) : 0
  implicitHeight: Math.max(12, (bar ? bar.barSize : 28) - 16)

  Behavior on implicitWidth {
    NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
  }

  Row {
    anchors.centerIn: parent
    spacing: 2

    Repeater {
      model: 4

      Rectangle {
        id: vBar
        required property int index
        width: 2.5
        radius: 1.25
        color: root.themeAccent
        anchors.bottom: parent.bottom
        height: 4

        readonly property int loMin: index === 0 ? 4 : (index === 1 ? 3 : (index === 2 ? 5 : 4))
        readonly property int hiMax: index === 0 ? 11 : (index === 1 ? 14 : (index === 2 ? 10 : 13))
        readonly property int animDuration: index === 0 ? 380 : (index === 1 ? 460 : (index === 2 ? 320 : 500))

        Behavior on height {
          enabled: !root.playing
          NumberAnimation { duration: 160; easing.type: Easing.OutCubic }
        }

        SequentialAnimation {
          running: root.playing
          loops: Animation.Infinite
          NumberAnimation {
            target: vBar; property: "height"
            from: vBar.loMin; to: vBar.hiMax
            duration: vBar.animDuration; easing.type: Easing.InOutQuad
          }
          NumberAnimation {
            target: vBar; property: "height"
            from: vBar.hiMax; to: vBar.loMin
            duration: vBar.animDuration; easing.type: Easing.InOutQuad
          }
          onRunningChanged: if (!running) vBar.height = 4
        }
      }
    }
  }
}
