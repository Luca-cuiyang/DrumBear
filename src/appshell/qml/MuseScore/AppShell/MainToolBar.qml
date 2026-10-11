/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2021 MuseScore Limited and others
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 3 as
 * published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

import Muse.Ui
import Muse.UiComponents
import DBScore.AppShell

Item {
    id: root

    width: radioButtonList.width + accountEntry.width + 40
    height: Math.max(radioButtonList.height, accountEntry.height)

    property alias navigation: navPanel

    property alias currentUri: toolBarModel.currentUri

    signal selected(string uri)

    function select(uri) {
        root.selected(uri)
    }

    function focusOnFirst() {
        var btn = radioButtonList.itemAtIndex(0) as PageTabButton
        if (btn) {
            btn.navigation.requestActive()
        }
    }

    MainToolBarModel {
        id: toolBarModel
    }

    Component.onCompleted: {
        toolBarModel.load()
    }

    NavigationPanel {
        id: navPanel
        name: "MainToolBar"
        enabled: root.enabled && root.visible
        accessible.name: qsTrc("appshell", "Main toolbar") + " " + navPanel.directionInfo
    }

    RadioButtonGroup {
        id: radioButtonList
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0

        model: toolBarModel

        width: Math.max(1, contentItem.childrenRect.width)
        height: Math.max(1, contentItem.childrenRect.height)

        delegate: PageTabButton {
            required property bool isTitleBold
            required property bool isChecked
            required title
            required property string uri
            required property int index

            ButtonGroup.group: radioButtonList.radioButtonGroup

            spacing: 0
            leftPadding: 12

            normalStateFont: isTitleBold ? ui.theme.largeBodyBoldFont : ui.theme.largeBodyFont

            navigation.name: title
            navigation.panel: navPanel
            navigation.order: index

            checked: isChecked

            onToggled: {
                root.selected(uri)
            }
        }
    }

    FlatButton {
        id: accountEntry

        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter

        text: qsTrc("appshell", "👤 登录")
        accentButton: false

        ToolTip.visible: accountEntry.hovered
        ToolTip.text: qsTrc("appshell", "点击进入账户中心")

        onClicked: {
            root.select("dbscore://account")
        }
    }
}
