pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import Quickshell.Io
import qs.Commons as Commons

// Now-playing content for the expanded Dynamic Island state. Hosted inside
// RunChrome's growing notch shape (not a separate popup), so it reads as
// one continuous surface morphing open from the screen edge.
Item {
  id: root

  required property var bar

  readonly property color themeAccent: (bar && bar.urgent)
    ? bar.urgent
    : (bar && bar.visualTokens && bar.visualTokens.seal
      ? bar.visualTokens.seal : Commons.Color.bar.active)

  readonly property var mediaService: bar && bar.shell
    && typeof bar.shell.firstPartyServiceFor === "function"
    ? bar.shell.firstPartyServiceFor("omarchy.media") : null
  readonly property var activePlayer: mediaService ? mediaService.activePlayer : null
  readonly property bool active: !!(activePlayer
    && (activePlayer.trackTitle || activePlayer.trackArtist))
  readonly property bool playing: active && activePlayer.isPlaying === true
  readonly property string title: activePlayer ? String(activePlayer.trackTitle || "") : ""
  readonly property string artist: activePlayer ? String(activePlayer.trackArtist || "") : ""
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
  readonly property bool canGoNext: !!(activePlayer && activePlayer.canGoNext)
  readonly property bool canGoPrevious: !!(activePlayer && activePlayer.canGoPrevious)
  readonly property real trackPosition: activePlayer && activePlayer.positionSupported
    ? Number(activePlayer.position) || 0 : 0
  readonly property real trackLength: activePlayer && activePlayer.lengthSupported
    ? Number(activePlayer.length) || 0 : 0
  readonly property real progressFraction: trackLength > 0
    ? Math.max(0, Math.min(1, trackPosition / trackLength)) : 0

  function runAction(action) {
    if (!mediaService || typeof mediaService.runAction !== "function") return
    var key = typeof mediaService.playerKey === "function"
      ? mediaService.playerKey(activePlayer) : ""
    mediaService.runAction(action, false, key)
  }

  function formatTime(seconds) {
    var s = Math.max(0, Math.round(Number(seconds) || 0))
    var m = Math.floor(s / 60)
    var r = s % 60
    return m + ":" + (r < 10 ? "0" + r : r)
  }

  Column {
    id: content
    anchors.top: parent.top
    anchors.left: parent.left
    anchors.right: parent.right
    anchors.topMargin: Commons.Style.space(8)
    anchors.leftMargin: Commons.Style.space(12)
    anchors.rightMargin: Commons.Style.space(12)
    spacing: Commons.Style.space(10)

    // Centered album art
    Rectangle {
      anchors.horizontalCenter: parent.horizontalCenter
      width: Commons.Style.space(88)
      height: Commons.Style.space(88)
      radius: Commons.Style.space(12)
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
        font.pixelSize: Commons.Style.space(36)
      }
    }

    // Title / artist
    Column {
      anchors.horizontalCenter: parent.horizontalCenter
      width: parent.width
      spacing: 2

      Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        text: root.title.length > 0 ? root.title : "Nothing playing"
        color: Commons.Color.foreground
        font.family: Commons.Style.font.family
        font.pixelSize: Commons.Style.font.body
        font.weight: Font.DemiBold
        elide: Text.ElideRight
      }

      Text {
        width: parent.width
        horizontalAlignment: Text.AlignHCenter
        visible: root.artist.length > 0
        text: root.artist
        color: root.themeAccent
        font.family: Commons.Style.font.family
        font.pixelSize: Commons.Style.font.caption
        elide: Text.ElideRight
      }
    }

    // Scrub bar with elapsed / total time
    Column {
      width: parent.width
      spacing: 4
      visible: root.trackLength > 0

      Rectangle {
        width: parent.width
        height: 4
        radius: 2
        color: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g,
          Commons.Color.foreground.b, 0.14)

        Rectangle {
          height: parent.height
          radius: 2
          width: Math.max(4, parent.width * root.progressFraction)
          color: root.themeAccent
        }
      }

      RowLayout {
        width: parent.width
        Text {
          text: root.formatTime(root.trackPosition)
          color: root.themeAccent
          font.family: Commons.Style.font.family
          font.pixelSize: Commons.Style.font.caption - 1
        }
        Item { Layout.fillWidth: true }
        Text {
          text: root.formatTime(root.trackLength)
          color: Commons.Color.muted
          font.family: Commons.Style.font.family
          font.pixelSize: Commons.Style.font.caption - 1
        }
      }
    }

    // Transport controls: Perfectly aligned horizontally and vertically
    Row {
      anchors.horizontalCenter: parent.horizontalCenter
      spacing: Commons.Style.space(24)

      // Previous Button
      Item {
        width: Commons.Style.space(36)
        height: Commons.Style.space(44)
        anchors.verticalCenter: parent.verticalCenter

        Text {
          anchors.centerIn: parent
          text: "skip_previous"
          color: root.canGoPrevious ? Commons.Color.foreground : Commons.Color.muted
          font.family: "Material Symbols Rounded"
          font.pixelSize: Commons.Style.space(26)
          opacity: root.canGoPrevious ? 1 : 0.4
        }

        MouseArea {
          anchors.fill: parent
          enabled: root.canGoPrevious
          cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
          onClicked: root.runAction("previous")
        }
      }

      // Play / Pause Circular Button
      Rectangle {
        width: Commons.Style.space(44)
        height: Commons.Style.space(44)
        radius: width / 2
        anchors.verticalCenter: parent.verticalCenter
        color: root.themeAccent

        Text {
          anchors.centerIn: parent
          text: root.playing ? "pause" : "play_arrow"
          color: Commons.Color.background
          font.family: "Material Symbols Rounded"
          font.pixelSize: Commons.Style.space(26)
        }

        MouseArea {
          anchors.fill: parent
          cursorShape: Qt.PointingHandCursor
          onClicked: root.runAction("playPause")
        }
      }

      // Next Button
      Item {
        width: Commons.Style.space(36)
        height: Commons.Style.space(44)
        anchors.verticalCenter: parent.verticalCenter

        Text {
          anchors.centerIn: parent
          text: "skip_next"
          color: root.canGoNext ? Commons.Color.foreground : Commons.Color.muted
          font.family: "Material Symbols Rounded"
          font.pixelSize: Commons.Style.space(26)
          opacity: root.canGoNext ? 1 : 0.4
        }

        MouseArea {
          anchors.fill: parent
          enabled: root.canGoNext
          cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
          onClicked: root.runAction("next")
        }
      }
    }
  }
}
