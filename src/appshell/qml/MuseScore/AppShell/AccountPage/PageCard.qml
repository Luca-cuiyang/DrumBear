/*
 * SPDX-License-Identifier: GPL-3.0-only
 * 个人中心卡片容器
 */
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import Muse.Ui
import Muse.UiComponents

Rectangle {
    id: root

    property bool accent: false

    Layout.fillWidth: true
    implicitHeight: cardContent.implicitHeight + 40
    radius: 16
    color: accent
           ? Utils.colorWithAlpha(ui.theme.accentColor, ui.theme.isDark ? 0.12 : 0.06)
           : ui.theme.popupBackgroundColor
    border.width: 1
    border.color: accent
                  ? Utils.colorWithAlpha(ui.theme.accentColor, 0.42)
                  : ui.theme.strokeColor

    Rectangle {
        width: 120
        height: width
        radius: width / 2
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.rightMargin: -42
        anchors.topMargin: -48
        z: -1
        visible: root.accent
        color: Utils.colorWithAlpha(ui.theme.accentColor, ui.theme.isDark ? 0.12 : 0.08)
    }

    default property alias content: cardContent.data

    ColumnLayout {
        id: cardContent

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 20
        spacing: 12
    }
}
