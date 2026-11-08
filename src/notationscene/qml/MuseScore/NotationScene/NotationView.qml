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
import QtQuick.Layouts
import QtQuick.Controls

import Muse.Ui
import Muse.UiComponents
import DBScore.NotationScene
import DBScore.Braille
import DBScore.Playback

import "internal"

FocusScope {
    id: root

    property alias name: notationView.objectName
    property alias publishMode: notationView.publishMode
    property alias readOnly: notationView.readOnly
    property bool showTabPanel: true
    property bool playerChromeVisible: false
    property bool webPlayerMode: false
    readonly property int playerChromeHeight: 60
    readonly property bool compactPortraitPlayer: webPlayerMode && width < height
    readonly property int playerTopChromeHeight: compactPortraitPlayer ? 35 : playerChromeHeight
    readonly property int playerBottomChromeHeight: playerChromeHeight

    property alias paintView: notationView

    property alias isNavigatorVisible: notationNavigator.visible
    property alias isBraillePanelVisible: brailleViewLoader.active
    property alias isMainView: notationView.isMainView

    property alias defaultNavigationControl: fakeNavCtrl
    property bool fittingPlayerPage: false
    property int playerFitAttempts: 0

    readonly property alias navigationSection: navSec
    readonly property alias navigationOrderEnd: searchPopup.navigationOrderEnd

    NavigationSection {
        id: navSec
        name: "NotationView"
        order: 5
        enabled: root.visible
    }

    QtObject {
        id: prv
        readonly property int scrollbarMargin: 4
    }

    NotationContextMenuModel {
        id: contextMenuModel
    }

    Component.onCompleted: {
        notationView.load()
    }

    Connections {
        target: notationView

        function onHasNotationChanged() {
            if (root.webPlayerMode && notationView.hasNotation) {
                playerFitTimer.restart()
                root.playerFitAttempts = 0
                playerFitSettleTimer.restart()
            }
        }

        function onViewportChanged() {
            if (root.webPlayerMode && notationView.hasNotation && !root.fittingPlayerPage) {
                playerFitTimer.restart()
            }
        }
    }

    Timer {
        id: playerFitTimer

        interval: 350
        repeat: false
        onTriggered: {
            if (!root.webPlayerMode || !notationView.hasNotation) {
                return
            }
            root.fittingPlayerPage = true
            notationView.fitPageToViewport()
            Qt.callLater(function() {
                root.fittingPlayerPage = false
            })
        }
    }

    Timer {
        id: playerFitSettleTimer

        interval: 350
        repeat: true
        onTriggered: {
            if (!root.webPlayerMode || !notationView.hasNotation
                    || root.playerFitAttempts >= 18) {
                stop()
                return
            }
            root.playerFitAttempts += 1
            notationView.fitPageToViewport()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: root.playerChromeVisible ? root.playerTopChromeHeight : 0
        anchors.bottomMargin: root.playerChromeVisible ? root.playerBottomChromeHeight : 0
        spacing: 0

        NotationSwitchPanel {
            id: tabPanel
            Layout.fillWidth: true
            visible: root.showTabPanel && !root.readOnly

            navigationPanel.section: navSec
            navigationPanel.order: 1
        }

        SeparatorLine { visible: tabPanel.visible }

        SplitView {
            id: splitView

            Layout.fillWidth: true
            Layout.fillHeight: true

            orientation: notationNavigator.orientation === Qt.Horizontal ? Qt.Vertical : Qt.Horizontal

            StyledViewScrollAndZoomArea {
                SplitView.fillWidth: true
                SplitView.fillHeight: true

                horizontalScrollbarSize: root.readOnly ? 0 : notationView.horizontalScrollbarSize
                startHorizontalScrollPosition: notationView.startHorizontalScrollPosition

                verticalScrollbarSize: root.readOnly ? 0 : notationView.verticalScrollbarSize
                startVerticalScrollPosition: notationView.startVerticalScrollPosition

                NotationPaintView {
                    id: notationView
                    anchors.fill: parent
                    portraitGrouped: root.compactPortraitPlayer

                    property NavigationPanel navigationPanel: NavigationPanel {
                        name: "ScoreView"
                        section: navSec
                        enabled: notationView.enabled && notationView.visible
                        direction: NavigationPanel.Both
                        order: tabPanel.navigationPanel.order + 1
                    }

                    NavigationControl {
                        id: fakeNavCtrl
                        name: "Score"
                        enabled: notationView.enabled && notationView.visible

                        panel: notationView.navigationPanel
                        order: 1

                        onActiveChanged: {
                            if (fakeNavCtrl.active) {
                                notationView.forceFocusIn()

                                if (notationView.navigationPanel.highlight) {
                                    notationView.selectOnNavigationActive()
                                }
                            } else {
                                notationView.focus = false
                            }
                        }
                    }

                    NavigationFocusBorder {
                        navigationCtrl: fakeNavCtrl
                        drawOutsideParent: false
                    }

                    Rectangle {
                        id: playbackCursor
                        z: 10

                        Component.onCompleted: {
                            notationView.setPlaybackCursorItem(playbackCursor)
                        }
                    }

                    onActiveFocusRequested: {
                        fakeNavCtrl.requestActive()
                    }

                    onShowContextMenuRequested: function (elementType, viewPos) {
                        contextMenuModel.loadItems(elementType)
                        contextMenuLoader.show(viewPos, contextMenuModel.items)
                    }

                    onHideContextMenuRequested: {
                        contextMenuLoader.close()
                    }

                    onShowSearchRequested: {
                        searchPopup.show()        
                    }

                    onShowElementPopupRequested: function (popupType) {
                        popUpLoader.updateShow(popupType);
                    }

                    onHideElementPopupRequested: {
                        popUpLoader.updateShow(AbstractElementPopupModel.TYPE_UNDEFINED);
                    }

                    onViewportChanged: {
                        notationNavigator.setCursorRect(viewport)
                    }

                    ContextMenuLoader {
                        id: contextMenuLoader

                        onHandleMenuItem: function(itemId) {
                            contextMenuModel.handleMenuItem(itemId)
                        }

                        onOpened: notationView.onContextMenuIsOpenChanged(true)
                        onClosed: notationView.onContextMenuIsOpenChanged(false)
                    }

                    ElementPopupLoader {
                        id: popUpLoader

                        notationViewNavigationSection: navSec
                        navigationOrderStart: notationView.navigationPanel.order + 1

                        property int popupType: AbstractElementPopupModel.TYPE_UNDEFINED
                        property bool updateShowScheduled: false

                        function updateShow(popupType) {
                            this.popupType = popupType;
                            if (!updateShowScheduled) {
                                Qt.callLater(doUpdateShow)
                                updateShowScheduled = true;
                            }
                        }

                        function doUpdateShow() {
                            updateShowScheduled = false;

                            if (popupType !== AbstractElementPopupModel.TYPE_UNDEFINED) {
                                show(popupType);
                            } else {
                                close();
                            }
                        }

                        onOpened: function(popupType) {
                            notationView.onElementPopupIsOpenChanged(popupType)
                        }

                        onClosed: {
                            notationView.onElementPopupIsOpenChanged(AbstractElementPopupModel.TYPE_UNDEFINED)
                        }
                    }

                    NotationRegionsBeingProcessedView {
                        notationViewRect: Qt.rect(notationView.x, notationView.y, notationView.width, notationView.height)
                        notationViewMatrix: notationView.matrix
                    }
                }

                onPinchToZoom: function(scale, pos) {
                    if (!root.readOnly) {
                        notationView.pinchToZoom(scale, pos)
                    }
                }

                onScrollHorizontal: function(newPos) {
                    if (!root.readOnly) {
                        notationView.scrollHorizontal(newPos)
                    }
                }

                onScrollVertical: function(newPos) {
                    if (!root.readOnly) {
                        notationView.scrollVertical(newPos)
                    }
                }
            }

            Loader {
                id: notationNavigator

                readonly property NotationNavigator navigatorItem: item as NotationNavigator

                property var orientation: navigatorItem?.orientation ?? Qt.Horizontal

                visible: false

                SplitView.preferredHeight: 100
                SplitView.preferredWidth: 100
                SplitView.minimumWidth: 30
                SplitView.minimumHeight: 30

                sourceComponent: visible ? navigatorComp : null

                function setCursorRect(viewport) {
                    if (navigatorItem) {
                        navigatorItem.setCursorRect(viewport)
                    }
                }
            }

            Loader {
                id: brailleViewLoader

                readonly property int navigationOrder: popUpLoader.navigationOrderEnd + 1

                active: false
                visible: active

                SplitView.fillWidth: true
                SplitView.preferredHeight: 50
                SplitView.minimumHeight: 30

                sourceComponent: BrailleView {
                    navigationPanel.section: navSec
                    navigationPanel.order: brailleViewLoader.navigationOrder

                    navigationPanel.onActiveChanged: function (active) {
                        if (active) {
                            notationView.navigationPanel.setActive(false);
                            fakeNavCtrl.setActive(false);
                        }
                    }
                }
            }

            Component {
                id: navigatorComp

                NotationNavigator {

                    property bool isVertical: orientation === Qt.Vertical

                    objectName: root.name + "Navigator"

                    Component.onCompleted: {
                        load()
                    }

                    onMoveNotationRequested: function(dx, dy) {
                        notationView.moveCanvas(dx, dy)
                    }
                }
            }

            handle: Rectangle {
                id: resizingHandle

                implicitWidth: 4
                implicitHeight: 4

                color: ui.theme.strokeColor

                states: [
                    State {
                        name: "PRESSED"
                        when: resizingHandle.SplitHandle.pressed
                        PropertyChanges {
                            target: resizingHandle
                            opacity: ui.theme.accentOpacityHit
                        }
                    },
                    State {
                        name: "HOVERED"
                        when: resizingHandle.SplitHandle.hovered
                        PropertyChanges {
                            target: resizingHandle
                            opacity: ui.theme.accentOpacityHover
                        }
                    }
                ]
            }
        }

        SearchPopup {
            id: searchPopup

            Layout.fillWidth: true

            navigationPanel.section: navSec
            navigationOrderStart: brailleViewLoader.navigationOrder + 1

            onClosed: {
                fakeNavCtrl.requestActive()
            }
        }
    }

    Rectangle {
        id: playerTopBar

        visible: root.playerChromeVisible
        x: 0
        y: 0
        width: root.width
        height: root.playerTopChromeHeight
        z: 200
        color: root.compactPortraitPlayer ? "#241b16" : ui.theme.backgroundSecondaryColor

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: ui.theme.strokeColor
        }

        StyledTextLabel {
            anchors.left: parent.left
            anchors.leftMargin: 20
            anchors.verticalCenter: parent.verticalCenter
            text: root.compactPortraitPlayer ? "DB Player 练鼓神器" : "DB player"
            font: Qt.font(Object.assign({}, ui.theme.bodyBoldFont, {
                family: "Noto Sans CJK SC"
            }))
            color: root.compactPortraitPlayer ? "#ffc18f" : ui.theme.fontPrimaryColor
        }

        StyledTextLabel {
            visible: root.compactPortraitPlayer
            width: 80
            anchors.right: parent.right
            anchors.rightMargin: 20
            anchors.verticalCenter: parent.verticalCenter
            text: Number(playerPlaybackToolBar.playbackModel.measureNumber)
                  + "." + Number(playerPlaybackToolBar.playbackModel.beatNumber)
            font: Qt.font(Object.assign({}, ui.theme.bodyBoldFont, {
                family: "Noto Sans CJK SC"
            }))
            color: "#ffc18f"
            horizontalAlignment: Text.AlignRight
        }

        Rectangle {
            visible: root.compactPortraitPlayer
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 2
            color: "#3a2d25"
        }

        Rectangle {
            visible: root.compactPortraitPlayer
            anchors.left: parent.left
            anchors.bottom: parent.bottom
            width: parent.width * Math.max(
                       0,
                       Math.min(1, playerPlaybackToolBar.playbackModel.playPosition))
            height: 2
            color: "#e88024"
        }
    }

    Rectangle {
        id: playerBottomBar

        visible: root.playerChromeVisible
        x: 0
        y: root.height - height
        width: root.width
        height: root.playerBottomChromeHeight
        z: 200
        color: ui.theme.backgroundSecondaryColor

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: 1
            color: ui.theme.strokeColor
            visible: true
        }

        PlaybackToolBar {
            id: playerPlaybackToolBar

            anchors.bottom: parent.bottom
            anchors.bottomMargin: 15
            anchors.horizontalCenter: parent.horizontalCenter
            width: Math.min(parent.width - 10, 620)
            height: 30
            floating: false
            compactMode: root.compactPortraitPlayer
        }
    }
}
