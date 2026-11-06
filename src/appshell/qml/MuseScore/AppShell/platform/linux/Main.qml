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
 
import QtQuick

import Muse.Ui
import Muse.UiComponents

AppWindow {
    id: root

    readonly property bool studioPlayerMode:
        WebAppMode.studioPlayerMode
        || Qt.application.arguments.indexOf("--db-product-mode=studio-player") !== -1

    Loader {
        id: appMenuBar

        visible: !root.studioPlayerMode
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
    }

    Loader {
        id: platformMenuBar

        active: !root.studioPlayerMode
    }

    Component.onCompleted: {
        platformMenuBar.setSource("../PlatformMenuBar.qml");
        if (platformMenuBar.item.available) {
            platformMenuBar.item.load();
            appMenuBar.active = 0;
        } else {
            appMenuBar.setSource("../AppMenuBar.qml", { "appWindow": root });
            platformMenuBar.active = 0;
        }

        window.init()
    }

    WindowContent {
        id: window

        anchors.top: appMenuBar.visible ? appMenuBar.bottom : parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
    }
}
