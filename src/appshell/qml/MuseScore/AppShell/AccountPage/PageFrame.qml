/*
 * SPDX-License-Identifier: GPL-3.0-only
 * 个人中心页面容器
 */
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import Muse.Ui
import Muse.UiComponents

Flickable {
    id: root

    property string title: ""

    default property alias content: contentColumn.data

    contentWidth: width
    contentHeight: contentColumn.implicitHeight + 56
    clip: true

    ColumnLayout {
        id: contentColumn

        width: parent.width
        anchors.margins: 28
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: 16

        StyledTextLabel {
            text: root.title
            font: ui.theme.titleBoldFont
        }
    }
}
