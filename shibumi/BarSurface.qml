pragma ComponentBehavior: Bound

import QtQuick
import qs.Commons as Commons
import "../../core" as Core
import "../../core/RunGeometry.js" as RunGeometry
import "../../core/ResponsiveLayout.js" as ResponsiveLayout
import "." as Shibumi

Item {
  id: root

  required property var bar
  property var layoutSession: null
  property string screenName: ""
  readonly property int responsiveStage: contentLoader.item
    && "narrowStage" in contentLoader.item
      ? Number(contentLoader.item.narrowStage) || 0 : 0
  readonly property var responsiveProbe: contentLoader.item
    && "responsiveProbe" in contentLoader.item
      ? contentLoader.item.responsiveProbe : ({})
  readonly property var reactorFacade: bar && bar.shell
    && typeof bar.shell.serviceFor === "function"
    ? bar.shell.serviceFor("hancore.shibumi.reactor") : null
  readonly property int reactorMode: reactorFacade
    ? Number(reactorFacade.mode || 0) : 0
  readonly property bool layoutProtected: bar.layoutController
    && "activeLayoutProtected" in bar.layoutController
    && bar.layoutController.activeLayoutProtected === true
  readonly property bool layoutChangesAllowed:
    layoutSession && layoutSession.editing || !layoutProtected
  readonly property real nowPlayingExpandLevel: contentLoader.item
    && "nowPlayingExpandLevel" in contentLoader.item
    ? Number(contentLoader.item.nowPlayingExpandLevel) || 0 : 0
  readonly property bool nowPlayingHovered: contentLoader.item
    && "nowPlayingHovered" in contentLoader.item
    ? (contentLoader.item.nowPlayingHovered === true) : false

  function checkNotchHover(mouseX) {
    if (contentLoader.item && typeof contentLoader.item.checkNotchHover === "function") {
      contentLoader.item.checkNotchHover(mouseX)
    }
  }
  focus: layoutSession && layoutSession.editing

  Loader {
    id: contentLoader
    anchors.fill: parent
    sourceComponent: root.bar.vertical ? verticalContent : horizontalContent
  }

  Component {
    id: nowPlayingContentComponent

    Shibumi.NowPlayingExpandedContent {
      bar: root.bar
    }
  }

  MouseArea {
    anchors.fill: parent
    acceptedButtons: Qt.LeftButton
    z: -10

    onClicked: {
      if (root.layoutSession && root.layoutSession.editing)
        root.layoutSession.setEditing(false)
    }
    onDoubleClicked: {
      if (root.layoutSession) root.layoutSession.setEditing(true)
    }
  }

  Keys.onEscapePressed: {
    if (root.layoutSession) root.layoutSession.setEditing(false)
  }

  Connections {
    target: root.layoutSession

    function onEditingChanged() {
      if (root.layoutSession && root.layoutSession.editing)
        root.forceActiveFocus()
    }
  }

  Component {
    id: horizontalContent

    Item {
      id: horizontalSurface

      // Eases from 0 (collapsed pill) to 1 (fully expanded Dynamic Island)
      // while the pointer hovers the now-playing pill or the space the
      // notch opens into.
      property real nowPlayingExpandLevel: 0
      readonly property bool nowPlayingHovered: nowPlayingHoverArea.containsMouse

      function checkNotchHover(mouseX) {
        var notchLeft = notchLeftEdge - 30
        var notchRight = notchRightEdge + 30
        if (mouseX >= notchLeft && mouseX <= notchRight) {
          if (nowPlayingArt && nowPlayingArt.active) {
            nowPlayingCollapseTimer.stop()
            horizontalSurface.nowPlayingExpandLevel = 1
          }
        }
      }
      Behavior on nowPlayingExpandLevel {
        NumberAnimation { duration: 340; easing.type: Easing.OutExpo }
      }

      // In V1, the notch has a visual width of 300px. Anchor left and right
      // regions relative to the outer edges of the notch with generous padding.
      readonly property real notchVisualWidth: 300
      readonly property real notchLeftEdge: Math.round((width - notchVisualWidth) / 2)
      readonly property real notchRightEdge: notchLeftEdge + notchVisualWidth
      readonly property real notchPadding: Commons.Style.space(8)

      readonly property int frameInset: root.bar.visualTokens.islandInsetX
      readonly property int contentInset:
        root.bar.visualTokens.islandContentInsetX !== undefined
          ? root.bar.visualTokens.islandContentInsetX : Commons.Style.space(4)
      readonly property int cutPadding: Commons.Style.space(4)
      readonly property int centerGap: Commons.Style.space(12)
      readonly property string shellStyle:
        ["shibumi", "full", "fit", "dock", "notch"]
          .indexOf(String(root.bar.visualTokens.shellStyle || "")) >= 0
          ? String(root.bar.visualTokens.shellStyle) : "shibumi"
      readonly property bool shibumiShell: shellStyle === "shibumi"
      readonly property bool compactShell:
        ["fit", "dock", "notch"].indexOf(shellStyle) >= 0
      readonly property real naturalShellWidth:
        leftGroups.budgetWidthForStage(0) + leftExtras.width
        + centerGroups.budgetWidthForStage(0) + centerExtras.width
        + rightExtras.width + rightGroups.budgetWidthForStage(0)
        + leftGroups.editingWidthOverhead
        + centerGroups.editingWidthOverhead
        + rightGroups.editingWidthOverhead
        + 2 * centerGap + 2 * contentInset
        + (shellStyle === "notch"
          ? 2 * root.bar.visualTokens.shellWingWidth : 0)
      readonly property real shellWidth: shibumiShell
        ? Math.max(0, width - 2 * frameInset)
        : compactShell ? Math.min(width - 2 * frameInset,
            Math.max(Commons.Style.space(80), naturalShellWidth))
        : width
      readonly property real responsiveCapacity: compactShell
        ? Math.max(0, width - 2 * frameInset) : shellWidth
      readonly property real shellX: shibumiShell ? frameInset
        : Math.round((width - shellWidth) / 2)
      readonly property real shellContentInset: contentInset
        + (shellStyle === "notch"
          ? root.bar.visualTokens.shellWingWidth : 0)
      readonly property real measuredCenterSpan: Math.max(0,
        rightRegion.x - (leftRegion.x + leftRegion.width) - 2 * centerGap)
      readonly property real centerAvailableWidth:
        ResponsiveLayout.centerAvailableWidth(compactShell, width,
          frameInset, shellContentInset, leftRegion.width, rightRegion.width,
          centerGap, measuredCenterSpan, centerExtras.width)
      property int narrowStage: 0
      readonly property real sideMargin: shellX + shellContentInset
      readonly property real responsiveSideInset: shellContentInset
      readonly property real centerFloorWidth: Math.max(80,
        Number(centerGroups.minimumResponsiveWidth) || 0)
      readonly property var narrowCandidateWidths: [0, 1, 2, 3].map(function(stage) {
        return leftGroups.budgetWidthForStage(stage)
          + rightGroups.budgetWidthForStage(stage)
          + horizontalSurface.centerFloorWidth
          + leftExtras.width + centerExtras.width + rightExtras.width
          + 2 * horizontalSurface.centerGap
          + 2 * horizontalSurface.responsiveSideInset
      })
      readonly property var responsiveProbe: ({
        shellWidth: Math.round(shellWidth),
        capacity: Math.round(responsiveCapacity),
        stage: narrowStage,
        candidates: narrowCandidateWidths.map(function(value) {
          return Math.round(Number(value) || 0)
        }),
        left: leftGroups.stageBudgetWidths,
        right: rightGroups.stageBudgetWidths,
        extras: [leftExtras.width, centerExtras.width, rightExtras.width],
        centerFloor: Math.round(centerFloorWidth),
        centerAvailable: Math.round(centerAvailableWidth)
      })
      readonly property real idealCenterX: Math.round((width - centerRegion.width) / 2)
      readonly property real minCenterX: Math.round(leftRegion.x + leftRegion.width + centerGap)
      readonly property real maxCenterX: Math.round(rightRegion.x - centerGap - centerRegion.width)
      readonly property real centerTargetX: maxCenterX < minCenterX
        ? Math.round((minCenterX + maxCenterX) / 2)
        : Math.max(minCenterX, Math.min(idealCenterX, maxCenterX))
      readonly property var runs: {
        void(leftGroups.groupGeometry)
        void(rightGroups.groupGeometry)
        void(leftRegion.x)
        void(leftRegion.width)
        void(centerRegion.x)
        void(centerRegion.width)
        void(rightRegion.x)
        void(rightRegion.width)
        void(runChrome.width)
        void(root.bar.layoutController.splits)
        return RunGeometry.compute({
          width: runChrome.width,
          padding: cutPadding,
          sections: [
            {
              x: leftRegion.x + leftGroups.x - runChrome.x,
              groups: leftGroups.groupGeometry,
              splits: root.bar.layoutController.splits.left
            },
            {
              x: rightRegion.x + rightGroups.x - runChrome.x,
              groups: rightGroups.groupGeometry,
              splits: root.bar.layoutController.splits.right
            }
          ],
          left: leftRegion.width > 0.5 ? {
            x: leftRegion.x - runChrome.x,
            width: leftRegion.width
          } : null,
          center: {
            x: horizontalSurface.notchLeftEdge - runChrome.x,
            width: horizontalSurface.notchVisualWidth
          },
          right: rightRegion.width > 0.5 ? {
            x: rightRegion.x - runChrome.x,
            width: rightRegion.width
          } : null,
          boundaries: root.bar.layoutController.splits.boundaries
        })
      }

      function toggleBoundary(index) {
        if (!root.layoutChangesAllowed) return false
        return root.bar.layoutController.toggleSplit(
          "boundaries", index,
          root.layoutSession && root.layoutSession.editing)
      }

      function updateNarrowStage() {
        narrowStage = ResponsiveLayout.nextNarrowStage(narrowStage,
          responsiveCapacity, narrowCandidateWidths)
      }

      function scheduleNarrowUpdate() { narrowTimer.restart() }

      function resetResponsiveProbe() {
        narrowStage = 0
        scheduleNarrowUpdate()
      }

      onWidthChanged: scheduleNarrowUpdate()
      onNarrowCandidateWidthsChanged: scheduleNarrowUpdate()
      Component.onCompleted: scheduleNarrowUpdate()

      Timer {
        id: narrowTimer
        interval: 80
        onTriggered: horizontalSurface.updateNarrowStage()
      }

      Timer {
        id: responsiveResetTimer
        interval: 220
        onTriggered: horizontalSurface.resetResponsiveProbe()
      }

      Connections {
        target: root.bar && root.bar.shell
          && typeof root.bar.shell.serviceFor === "function"
          ? root.bar.shell.serviceFor("hancore.shibumi.state") : null
        ignoreUnknownSignals: true
        function onRevisionChanged() { responsiveResetTimer.restart() }
      }

      Connections {
        target: root.bar
        ignoreUnknownSignals: true
        function onLayoutConfigChanged() { responsiveResetTimer.restart() }
      }

      Shibumi.RunChrome {
        id: runChrome

        bar: root.bar
        screenName: root.screenName
        screenX: horizontalSurface.shellX
        runs: horizontalSurface.runs
        visible: true
        x: horizontalSurface.shellX
        width: Math.max(0, horizontalSurface.shellWidth)
        height: horizontalSurface.shibumiShell
          ? Math.min(parent.height, root.bar.visualTokens.islandHeight)
          : parent.height
        y: horizontalSurface.shibumiShell
          ? (root.bar.position === "bottom" ? 0
            : root.bar.visualTokens.islandOffsetY)
          : (root.bar.position === "bottom"
            ? parent.height - height : 0)
        z: 0
        nowPlayingExpandProgress: horizontalSurface.nowPlayingExpandLevel
        nowPlayingExpandedContent: nowPlayingContentComponent
      }

      Rectangle {
        x: runChrome.x - Commons.Style.space(3)
        y: runChrome.y - Commons.Style.space(3)
        width: runChrome.width + Commons.Style.space(6)
        height: runChrome.height + Commons.Style.space(6)
        visible: root.layoutSession && root.layoutSession.editing
        color: "transparent"
        border.width: 1
        border.color: root.bar.urgent
        radius: root.bar.layoutController.v2Mode
          ? 0 : root.bar.visualTokens.islandRadius + Commons.Style.space(2)
        z: 80

        SequentialAnimation on opacity {
          running: root.layoutSession && root.layoutSession.editing
          loops: Animation.Infinite
          NumberAnimation {
            from: 1
            to: 0.45
            duration: 900
            easing.type: Easing.InOutSine
          }
          NumberAnimation {
            from: 0.45
            to: 1
            duration: 900
            easing.type: Easing.InOutSine
          }
        }
      }

      Loader {
        id: gapEffectsLoader

        active: !root.bar.barHidden
          && root.bar.layoutController.v2Mode !== true
          && root.reactorMode >= 1 && root.reactorMode <= 8
          && horizontalSurface.runs.length > 1
        x: runChrome.x
        y: runChrome.y
        width: runChrome.width
        height: runChrome.height
        z: 5
        sourceComponent: !active ? null
          : root.reactorMode >= 7 ? reactorEventComponent
          : gapEffectsComponent

        Component {
          id: gapEffectsComponent

          Shibumi.GapEffectsLayer {
            bar: root.bar
            mode: root.reactorMode
            runs: horizontalSurface.runs
          }
        }

        Component {
          id: reactorEventComponent

          Shibumi.ReactorEventLayer {
            bar: root.bar
            service: root.reactorFacade
            runs: horizontalSurface.runs
            screenName: root.screenName
          }
        }
      }

      Row {
        id: leftRegion

        spacing: Commons.Style.space(8)
        anchors.verticalCenter: runChrome.verticalCenter
        x: horizontalSurface.shibumiShell
          ? Math.max(horizontalSurface.sideMargin, horizontalSurface.notchLeftEdge - width - horizontalSurface.notchPadding)
          : (horizontalSurface.shellX + horizontalSurface.shellContentInset)
        z: 10

        Behavior on x {
          NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
        }

        Shibumi.GroupSection {
          id: leftGroups
          anchors.verticalCenter: parent.verticalCenter
          bar: root.bar
          region: "left"
          screenName: root.screenName
          layoutSession: root.layoutSession
          visibilityStage: horizontalSurface.narrowStage
        }

        Core.BarSection {
          id: leftExtras
          anchors.verticalCenter: parent.verticalCenter
          bar: root.bar
          region: "left-extra"
          screenName: root.screenName
          entries: root.bar.unassignedLayoutEntries("left")
        }
      }

      Row {
        id: centerRegion

        anchors.verticalCenter: runChrome.verticalCenter
        // In V1, the notch extends up to the screen edge (y: 0); offset the
        // content up by half the island offset so it is centered in the notch.
        anchors.verticalCenterOffset: horizontalSurface.shibumiShell
          ? -Math.round(root.bar.visualTokens.islandOffsetY / 2) : 0
        x: Math.round((horizontalSurface.width - width) / 2)
        z: 10
        spacing: horizontalSurface.shibumiShell ? Commons.Style.space(4) : 0

        Behavior on x {
          NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
        }

        // Dynamic Island now-playing flank: album art to the left of the
        // clock/notch content, only rendered on the V1/Shibumi shell where
        // the notch gives it a natural home. Both flanks fade out as the
        // notch expands, since the expanded content shows its own art.
        Shibumi.NowPlayingAlbumArt {
          id: nowPlayingArt
          visible: horizontalSurface.shibumiShell
          anchors.verticalCenter: parent.verticalCenter
          bar: root.bar
          opacity: 1 - horizontalSurface.nowPlayingExpandLevel
        }

        Shibumi.GroupSection {
          id: centerGroups
          anchors.verticalCenter: parent.verticalCenter
          bar: root.bar
          region: "center"
          screenName: root.screenName
          layoutSession: root.layoutSession
          visibilityStage: horizontalSurface.narrowStage
          availableWidth: Math.max(1, horizontalSurface.centerAvailableWidth)
        }

        Core.BarSection {
          id: centerExtras
          anchors.verticalCenter: parent.verticalCenter
          bar: root.bar
          region: "center-extra"
          screenName: root.screenName
          entries: root.bar.unassignedLayoutEntries("center")
        }

        // Visualizer flank on the right of the clock/notch content.
        Shibumi.NowPlayingVisualizer {
          id: nowPlayingVisualizer
          visible: horizontalSurface.shibumiShell
          anchors.verticalCenter: parent.verticalCenter
          bar: root.bar
          opacity: 1 - horizontalSurface.nowPlayingExpandLevel
        }
      }

      // Collapse timer to avoid accidental collapse when moving cursor
      Timer {
        id: nowPlayingCollapseTimer
        interval: 400
        onTriggered: {
          if (!nowPlayingHoverArea.containsMouse) {
            horizontalSurface.nowPlayingExpandLevel = 0
          }
        }
      }

      // Hit area covering the collapsed pill plus the full space the notch
      // opens into while expanded, centered on the screen.
      MouseArea {
        id: nowPlayingHoverArea
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        readonly property real currentWidth: Math.max(centerRegion.width + Commons.Style.space(48), 350)
        x: Math.round((horizontalSurface.width - currentWidth) / 2)
        y: 0
        width: currentWidth
        height: horizontalSurface.nowPlayingExpandLevel > 0.01 ? 360 : (centerRegion.height + Commons.Style.space(12))
        z: 11
        propagateComposedEvents: true
        enabled: horizontalSurface.shibumiShell && nowPlayingArt.active
        onEntered: {
          nowPlayingCollapseTimer.stop()
          horizontalSurface.nowPlayingExpandLevel = 1
        }
        onExited: {
          nowPlayingCollapseTimer.restart()
        }
      }
      Row {
        id: rightRegion

        spacing: Commons.Style.space(8)
        anchors.verticalCenter: runChrome.verticalCenter
        x: horizontalSurface.shibumiShell
          ? Math.min(horizontalSurface.width - horizontalSurface.sideMargin - width, horizontalSurface.notchRightEdge + horizontalSurface.notchPadding)
          : (horizontalSurface.width - horizontalSurface.shellX - horizontalSurface.shellContentInset - width)
        z: 10

        Behavior on x {
          NumberAnimation { duration: 120; easing.type: Easing.OutCubic }
        }

        Shibumi.GroupSection {
          id: rightGroups
          anchors.verticalCenter: parent.verticalCenter
          bar: root.bar
          region: "right"
          screenName: root.screenName
          layoutSession: root.layoutSession
          visibilityStage: horizontalSurface.narrowStage
        }

        Core.BarSection {
          id: rightExtras
          anchors.verticalCenter: parent.verticalCenter
          bar: root.bar
          region: "right-extra"
          screenName: root.screenName
          entries: root.bar.unassignedLayoutEntries("right")
        }
      }
    }
  }

  Component {
    id: verticalContent

    Item {
      id: verticalSurface
      anchors.fill: parent
    }
  }
}
