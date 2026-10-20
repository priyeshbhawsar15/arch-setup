pragma ComponentBehavior: Bound

import QtQuick
import Quickshell.Hyprland
import qs.Commons as Commons

Item {
  id: root

  required property var bar
  property string region: ""
  property string screenName: ""
  property var entries: []
  readonly property Item contentItem: content.item

  readonly property bool isSideMonitor: {
    const name = String(root.screenName || "")
    if (name === "") return false
    const monitors = Hyprland.monitors ? (Hyprland.monitors.values || []) : []
    if (monitors.length <= 1) return false
    for (let index = 0; index < monitors.length; index++) {
      const monitor = monitors[index]
      if (String(monitor.name || "") === name) {
        if (String(monitor.description || "") === "@bar-main-description@") return false
        return true
      }
    }
    return false
  }

  readonly property bool isCenter: root.region.indexOf("center") >= 0

  visible: (!isSideMonitor || isCenter) && entries.length > 0
  implicitWidth: contentItem ? contentItem.implicitWidth : 0
  implicitHeight: contentItem ? contentItem.implicitHeight : 0
  width: implicitWidth
  height: implicitHeight

  Loader {
    id: content
    sourceComponent: root.bar.vertical ? verticalList : horizontalList
  }

  Component {
    id: horizontalList

    Row {
      spacing: root.isCenter ? 0 : Commons.Style.space(6)

      Repeater {
        model: root.entries

        Item {
          id: slotItem
          required property var modelData

          implicitWidth: root.isCenter
            ? widgetSlot.implicitWidth
            : widgetSlot.implicitWidth + Commons.Style.space(6)
          implicitHeight: root.isCenter
            ? widgetSlot.implicitHeight
            : Math.min(root.bar ? root.bar.barSize : 28, 28)
          anchors.verticalCenter: parent.verticalCenter

          // Solid background pill for non-center extra widgets (e.g. hyprmoncfg)
          Rectangle {
            anchors.fill: parent
            visible: !root.isCenter
            radius: root.bar && root.bar.visualTokens
              && root.bar.visualTokens.pillRadius !== undefined
              ? root.bar.visualTokens.pillRadius : Commons.Style.space(12)
            color: Commons.Color.background
            border.width: 1
            border.color: root.bar && root.bar.visualTokens
              && root.bar.visualTokens.islandBorder !== undefined
              ? root.bar.visualTokens.islandBorder
              : Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.16)
          }

          WidgetSlot {
            id: widgetSlot
            anchors.centerIn: parent
            bar: root.bar
            entry: slotItem.modelData
            region: root.region
            screenName: root.screenName
          }
        }
      }
    }
  }

  Component {
    id: verticalList

    Column {
      spacing: root.isCenter ? 0 : Commons.Style.space(6)

      Repeater {
        model: root.entries

        Item {
          id: vSlotItem
          required property var modelData

          implicitWidth: root.bar ? root.bar.barSize : 28
          implicitHeight: vWidgetSlot.implicitHeight + Commons.Style.space(6)

          Rectangle {
            anchors.fill: parent
            visible: !root.isCenter
            radius: Commons.Style.space(12)
            color: Commons.Color.background
            border.width: 1
            border.color: root.bar && root.bar.visualTokens
              && root.bar.visualTokens.islandBorder !== undefined
              ? root.bar.visualTokens.islandBorder
              : Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.16)
          }

          WidgetSlot {
            id: vWidgetSlot
            anchors.centerIn: parent
            bar: root.bar
            entry: vSlotItem.modelData
            region: root.region
            screenName: root.screenName
          }
        }
      }
    }
  }
}
