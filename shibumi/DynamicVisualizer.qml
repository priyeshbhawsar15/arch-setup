import QtQuick
import qs.Commons as Commons

Item {
  id: visualizer

  property bool active: true
  property color barColor: Commons.Color.accent

  implicitWidth: 20
  implicitHeight: 18

  Row {
    anchors.centerIn: parent
    spacing: 2

    Repeater {
      model: 4

      Rectangle {
        id: vBar
        width: 2.5
        height: 6
        radius: 1.25
        color: visualizer.barColor
        anchors.verticalCenter: parent.verticalCenter

        SequentialAnimation on height {
          running: visualizer.active
          loops: Animation.Infinite
          NumberAnimation {
            from: index === 0 ? 4 : (index === 1 ? 12 : (index === 2 ? 8 : 14))
            to: index === 0 ? 14 : (index === 1 ? 4 : (index === 2 ? 14 : 6))
            duration: index === 0 ? 380 : (index === 1 ? 450 : (index === 2 ? 320 : 490))
            easing.type: Easing.InOutQuad
          }
          NumberAnimation {
            from: index === 0 ? 14 : (index === 1 ? 4 : (index === 2 ? 14 : 6))
            to: index === 0 ? 4 : (index === 1 ? 12 : (index === 2 ? 8 : 14))
            duration: index === 0 ? 380 : (index === 1 ? 450 : (index === 2 ? 320 : 490))
            easing.type: Easing.InOutQuad
          }
        }
      }
    }
  }
}
