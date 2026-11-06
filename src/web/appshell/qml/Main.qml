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

import Muse.Interactive

import DBScore.Playback 1.0

AppWindow {
    id: root

    flags: Qt.FramelessWindowHint

    readonly property bool studioPlayerMode:
        Qt.application.arguments.indexOf("--db-product-mode=studio-player") !== -1

    InteractiveProvider {
        id: interactiveProvider
        topParent: root

        onRequestedDockPage: function(uri, params) {
            Qt.callLater(interactiveProvider.onPageOpened)
        }
    }

    PlaybackToolBar {
        id: playbackToolBar

        visible: !root.studioPlayerMode
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 8
        anchors.rightMargin: 8
    }

    NotationFrame {
        playerMode: root.studioPlayerMode

        anchors.top: root.studioPlayerMode ? parent.top : playbackToolBar.bottom
        anchors.topMargin: root.studioPlayerMode ? 0 : 8
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
    }
}
