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

    Layout.fillWidth: true
    implicitHeight: cardContent.implicitHeight + 40
    radius: 12
    color: ui.theme.backgroundSecondaryColor

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
