pragma ComponentBehavior: Bound

import QtQuick
import Quickshell
import Quickshell.Wayland

PanelWindow {
  id: barWindow

  required property var bar
  readonly property bool validScreen: screen !== null
    && screen.name !== ""
    && screen.width > 0
    && screen.height > 0
  readonly property var layoutSession: dragSession
  readonly property real surfaceWidth: barSurfaceLoader.item
    ? Number(barSurfaceLoader.item.width) || 0 : 0
  readonly property int responsiveStage: barSurfaceLoader.item
    && "responsiveStage" in barSurfaceLoader.item
      ? Number(barSurfaceLoader.item.responsiveStage) || 0 : 0
  readonly property var responsiveProbe: barSurfaceLoader.item
    && "responsiveProbe" in barSurfaceLoader.item
      ? barSurfaceLoader.item.responsiveProbe : ({})

  property bool hoverRevealed: false

  Timer {
    id: autohideHideTimer
    interval: 1000
    onTriggered: {
      if (!hoverArea.containsMouse && !barWindow.nowPlayingExpanded && !barWindow.nowPlayingHovered && (!bar || typeof bar.activePopoutForScreen !== "function"
            || !bar.activePopoutForScreen(barWindow.screen ? barWindow.screen.name : ""))) {
        barWindow.hoverRevealed = false
      }
    }
  }

  function requestHide() {
    if (bar && bar.barAutohideEnabled) autohideHideTimer.restart()
  }

  function requestShow() {
    autohideHideTimer.stop()
    barWindow.hoverRevealed = true
  }

  readonly property bool autohideActive: bar && bar.barAutohideEnabled === true
  readonly property bool nowPlayingHovered: barSurfaceLoader.item
    && "nowPlayingHovered" in barSurfaceLoader.item
    ? (barSurfaceLoader.item.nowPlayingHovered === true) : false
  readonly property bool autohideRevealed: !autohideActive || hoverRevealed || nowPlayingExpanded || nowPlayingHovered || (dragSession && dragSession.editing)
  readonly property bool nowPlayingExpanded: barSurfaceLoader.item
    && "nowPlayingExpandLevel" in barSurfaceLoader.item
    ? (barSurfaceLoader.item.nowPlayingExpandLevel > 0.01) : false

  visible: bar.hostReady && bar.styleReady && validScreen && !bar.barHidden
    && windowRecovery.recoveryVisible
  // Match the original V1 input model: keep one stable screen-sized surface
  // and change only its input region. This avoids compositor resize flashes
  // while allowing bar drag, Escape, and outside-click dismissal to share one
  // focus owner during editing.
  implicitWidth: bar.vertical && validScreen ? screen.width : 0
  implicitHeight: !bar.vertical && validScreen ? screen.height : 0
  color: "transparent"
  surfaceFormat.opaque: false

  anchors {
    top: bar.position === "top" || bar.vertical
    bottom: bar.position === "bottom" || bar.vertical
    left: bar.position === "left" || !bar.vertical
    right: bar.position === "right" || !bar.vertical
  }

  WlrLayershell.namespace: "shibumi-bar"
  WlrLayershell.layer: WlrLayer.Top
  exclusiveZone: autohideActive ? 0 : bar.barExclusiveSize
  WlrLayershell.keyboardFocus: dragSession.editing
    ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

  mask: Region {
    x: dragSession.editing ? 0
      : barWindow.bar.vertical && barWindow.bar.position === "right"
        ? Math.max(0, barWindow.width - barWindow.bar.barSize) : 0
    y: dragSession.editing ? 0
      : !barWindow.bar.vertical && barWindow.bar.position === "bottom"
        ? Math.max(0, barWindow.height - barWindow.bar.barSize) : 0
    width: dragSession.editing || !barWindow.bar.vertical
      ? barWindow.width : barWindow.bar.barSize
    height: dragSession.editing || barWindow.bar.vertical
      ? barWindow.height
      : (barWindow.nowPlayingExpanded ? 380 : (barWindow.autohideActive && !barWindow.autohideRevealed ? 8 : barWindow.bar.barSize))
  }

  WindowRecovery {
    id: windowRecovery
    targetWindow: barWindow
    targetScreen: barWindow.screen
    recoveryAllowed: barWindow.bar.hostReady
      && barWindow.bar.styleReady
      && !barWindow.bar.barHidden
  }

  DragSession {
    id: dragSession
    layoutController: barWindow.bar.layoutController
    screenName: barWindow.screen ? String(barWindow.screen.name || "") : ""
  }

  Component.onCompleted: bar.registerLayoutSession(dragSession)
  Component.onDestruction: {
    if (typeof bar.releasePopoutsForScreen === "function")
      bar.releasePopoutsForScreen(dragSession.screenName)
    bar.unregisterLayoutSession(dragSession)
  }

  DragGhostPanel {
    bar: barWindow.bar
    layoutSession: dragSession
    targetScreen: barWindow.screen
  }

  HostedPanelConnector {
    bar: barWindow.bar
    targetScreen: barWindow.screen
  }

  MouseArea {
    id: hoverArea
    // While hidden, this owns the thin edge sensor. Once revealed it must sit
    // behind the bar surface, otherwise it blocks the notch's own hover area
    // and the media control centre can never expand.
    z: barWindow.autohideRevealed ? 0 : 100
    anchors.top: parent.top
    anchors.left: parent.left
    anchors.right: parent.right
    height: barWindow.autohideActive ? ((barWindow.autohideRevealed || barWindow.nowPlayingExpanded) ? barWindow.bar.barSize : 8) : 0
    hoverEnabled: true
    // This is a reveal sensor only. It must never consume clicks intended for
    // widgets once the bar is visible.
    acceptedButtons: Qt.NoButton
    onEntered: function() {
      barWindow.requestShow()
      if (barSurfaceLoader.item && typeof barSurfaceLoader.item.checkNotchHover === "function") {
        barSurfaceLoader.item.checkNotchHover(hoverArea.mouseX)
      }
    }
    onPositionChanged: function(mouse) {
      if (barSurfaceLoader.item && typeof barSurfaceLoader.item.checkNotchHover === "function") {
        barSurfaceLoader.item.checkNotchHover(mouse.x)
      }
    }
    onExited: barWindow.requestHide()
  }

  Rectangle {
    anchors.fill: parent
    visible: dragSession.editing
    color: "#000000"
    opacity: 0.34
    z: 1

    MouseArea {
      anchors.fill: parent
      acceptedButtons: Qt.LeftButton
      onClicked: dragSession.setEditing(false)
    }
  }

  Loader {
    id: barSurfaceLoader

    width: barWindow.bar.vertical ? barWindow.bar.barSize : parent.width
    height: barWindow.bar.vertical ? parent.height : (barWindow.nowPlayingExpanded ? 380 : barWindow.bar.barSize)
    x: barWindow.bar.vertical && barWindow.bar.position === "right"
      ? Math.max(0, parent.width - width) : 0
    y: !barWindow.bar.vertical && barWindow.bar.position === "bottom"
      ? Math.max(0, parent.height - height)
      : (barWindow.autohideActive && !barWindow.autohideRevealed ? -height : 0)

    Behavior on y {
      enabled: barWindow.autohideActive && !dragSession.editing
      NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
    }
    active: barWindow.bar.hostReady && barWindow.bar.styleReady
      && barWindow.validScreen && barWindow.bar.visualTokens !== null
    sourceComponent: active ? barWindow.bar.activeStyle.barSurfaceComponent : null
    z: 10
    onLoaded: {
      if (item && "layoutSession" in item) item.layoutSession = dragSession
      if (item && "screenName" in item)
        item.screenName = barWindow.screen ? String(barWindow.screen.name || "") : ""
    }
  }

  PopupWindow {
    id: tooltipWindow

    visible: barWindow.bar.styleReady
      && barWindow.bar.tooltipShown
      && barWindow.bar.targetBelongsToWindow(barWindow.bar.tooltipTarget, barWindow)
    color: "transparent"
    implicitWidth: tooltipSurfaceLoader.item
      ? Math.ceil(tooltipSurfaceLoader.item.implicitWidth)
      : 0
    implicitHeight: tooltipSurfaceLoader.item
      ? Math.ceil(tooltipSurfaceLoader.item.implicitHeight)
      : 0

    anchor {
      window: barWindow
      adjustment: PopupAdjustment.Slide
      edges: Edges.Top | Edges.Left
      gravity: Edges.Bottom | Edges.Right
      rect.width: 1
      rect.height: 1

      onAnchoring: {
        const target = barWindow.bar.tooltipTarget
        if (!barWindow.bar.targetBelongsToWindow(target, barWindow)) return

        let localX = target.width / 2 - tooltipWindow.implicitWidth / 2
        const gap = barWindow.bar.activeStyle.tooltipGap
        let localY = target.height + gap
        if (barWindow.bar.position === "bottom")
          localY = -tooltipWindow.implicitHeight - gap
        else if (barWindow.bar.position === "left") {
          localX = target.width + gap
          localY = target.height / 2 - tooltipWindow.implicitHeight / 2
        } else if (barWindow.bar.position === "right") {
          localX = -tooltipWindow.implicitWidth - gap
          localY = target.height / 2 - tooltipWindow.implicitHeight / 2
        }

        const point = barWindow.contentItem.mapFromItem(target, localX, localY)
        tooltipWindow.anchor.rect.x = Math.round(point.x)
        tooltipWindow.anchor.rect.y = Math.round(point.y)
      }
    }

    Loader {
      id: tooltipSurfaceLoader

      anchors.fill: parent
      active: barWindow.bar.styleReady
        && barWindow.bar.visualTokens !== null
      sourceComponent: active ? barWindow.bar.activeStyle.tooltipSurfaceComponent : null
    }
  }
}
