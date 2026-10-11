pragma ComponentBehavior: Bound

import QtQuick
import Quickshell.Io
import qs.Commons as Commons

// Small rounded album-art thumbnail shown to the left of the clock/notch
// content, only while a track is active. Mirrors the reference Dynamic
// Island layout: art on the left, visualizer on the right, clock centered.
Item {
  id: root

  required property var bar
  readonly property var mediaService: bar && bar.shell
    && typeof bar.shell.firstPartyServiceFor === "function"
    ? bar.shell.firstPartyServiceFor("omarchy.media") : null
  readonly property var activePlayer: mediaService ? mediaService.activePlayer : null
  readonly property bool active: !!(activePlayer
    && (activePlayer.trackTitle || activePlayer.trackArtist))
  property string resolvedArtUrl: ""
  readonly property string artUrl: {
    if (activePlayer && activePlayer.trackArtUrl && String(activePlayer.trackArtUrl).length > 0)
      return String(activePlayer.trackArtUrl)
    return resolvedArtUrl
  }

  Process {
    id: artResolverProcess
    command: ["python3", "/home/priyesh/.config/omarchy/plugins/hancore.shibumi.bar/scripts/jellyfin-art-resolver.py"]
    stdout: SplitParser {
      onRead: function(data) {
        var line = String(data).trim()
        if (line.length > 0) root.resolvedArtUrl = line
      }
    }
  }

  Timer {
    id: resolverTimer
    interval: 3000
    running: root.active && (!activePlayer || !activePlayer.trackArtUrl || String(activePlayer.trackArtUrl).length === 0)
    repeat: true
    triggeredOnStart: true
    onTriggered: {
      if (!artResolverProcess.running) artResolverProcess.running = true
    }
  }

  readonly property color themeAccent: (bar && bar.urgent)
    ? bar.urgent
    : (bar && bar.visualTokens && bar.visualTokens.seal
      ? bar.visualTokens.seal : Commons.Color.bar.active)

  readonly property int size: Math.max(16, (bar ? bar.barSize : 28) - 12)

  visible: active
  implicitWidth: active ? size + Commons.Style.space(6) : 0
  implicitHeight: size

  Behavior on implicitWidth {
    NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
  }

  Rectangle {
    id: frame
    anchors.verticalCenter: parent.verticalCenter
    anchors.left: parent.left
    width: root.size
    height: root.size
    radius: Commons.Style.space(6)
    color: Commons.Color.background
    border.width: 1
    border.color: Qt.rgba(root.themeAccent.r, root.themeAccent.g,
      root.themeAccent.b, 0.40)
    clip: true

    Image {
      anchors.fill: parent
      source: root.artUrl
      fillMode: Image.PreserveAspectCrop
      asynchronous: true
      cache: true
      visible: status === Image.Ready
    }

    Text {
      anchors.centerIn: parent
      visible: root.artUrl.length === 0
      text: "music_note"
      color: root.themeAccent
      font.family: "Material Symbols Rounded"
      font.pixelSize: Math.round(root.size * 0.55)
    }
  }
}
