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

import Muse.UiComponents
import Muse.Ui

import DBScore.NotationScene
import DBScore.Playback

Item {
    id: root

    property PlaybackToolBarModel playbackModel: null

    property NavigationPanel navPanel: null
    readonly property int navigationOrderEnd: tempoLoader.navigationOrderEnd

    property bool floating: false
    property bool compactMode: false

    readonly property real compactTempoWidth: 8 + tempoLoader.tempoViewWidth

    // Not `+ endSeparator.width`: this way, the separator itself is outside the view,
    // which means that it will be exactly at the position of the KDDockWidgets separator
    // between this toolbar and the undo/redo toolbar.
    width: root.compactMode ? buttonsListView.width + compactTempoWidth
                            : (endSeparator.visible ? endSeparator.x : tempoLoader.x + tempoLoader.width)
    height: 30

    ListView {
        id: buttonsListView

        anchors.left: parent.left

        width: contentWidth
        height: contentHeight

        contentHeight: root.height
        spacing: 4

        model: root.playbackModel

        orientation: Qt.Horizontal
        interactive: false

        readonly property int navigationOrderEnd: count

        delegate: FlatButton {
            id: btn

            required property MenuItem item
            required property int index

            readonly property bool textMarkerAction:
                item.id === "command://playback/loop-in"
                || item.id === "command://playback/loop-out"
            readonly property bool compactTextAction: root.compactMode
            readonly property bool textOnlyAction:
                compactTextAction || textMarkerAction
            readonly property string markerText:
                item.id === "command://playback/loop-in" ? "起点" : "终点"
            readonly property string compactText: {
                if (item.id === "command://playback/rewind") return "回退"
                if (item.id === "play-toggle") return item.checked ? "暂停" : "播放"
                if (item.id === "command://playback/loop-toggle") return "循环"
                if (item.id === "command://playback/loop-in") return "起点"
                if (item.id === "command://playback/loop-out") return "终点"
                if (item.id === "command://playback/metronome-toggle") return "节拍"
                if (item.id === "command://playback/repeats-toggle") return "反复"
                if (item.id === "drums-mute") return "鼓声"
                if (item.id === "accompaniment-mute") return "伴奏"
                return item.title
            }

            width: compactTextAction
                   ? (item.id === "play-toggle" ? 34 : 29)
                   : (textMarkerAction ? 38 : 30)
            height: width

            icon: Boolean(item) && !textOnlyAction ? item.icon : IconCode.NONE
            text: compactTextAction
                  ? compactText
                  : (textMarkerAction ? markerText : "")
            textFormat: Text.PlainText
            maximumLineCount: 1
            buttonType: textOnlyAction ? FlatButton.TextOnly : FlatButton.IconOnly
            contentItem: compactTextAction ? compactTextContent : null

            toolTipTitle: Boolean(item) ? item.title : ""
            toolTipDescription: Boolean(item) ? item.description : ""
            toolTipShortcut: Boolean(item) ? item.shortcuts : ""

            iconFont: ui.theme.toolbarIconsFont
            textFont: ui.theme.bodyBoldFont
            iconColor: root.compactMode
                       ? (accentButton ? "#ffffff" : "#f7ede4")
                       : ui.theme.fontPrimaryColor

            accentButton: (Boolean(item) && item.checked) || menuLoader.isMenuOpened
            accentColor: root.compactMode ? "#e88024" : ui.theme.accentColor
            transparent: !accentButton

            navigation.panel: root.navPanel
            navigation.name: toolTipTitle
            navigation.order: index
            accessible.name: (item.checkable ? (item.checked ? item.title + "  " + qsTrc("global", "On") :
                                                               item.title + "  " + qsTrc("global", "Off")) : item.title)

            Component {
                id: compactTextContent

                StyledTextLabel {
                    text: btn.text
                    color: btn.accentButton ? "#ffffff" : "#f7ede4"
                    font: Qt.font(Object.assign({}, ui.theme.bodyBoldFont, {
                        family: "Noto Sans CJK SC"
                    }))
                    textFormat: Text.PlainText
                    wrapMode: Text.NoWrap
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            onClicked: {
                if (menuLoader.isMenuOpened || item.subitems.length) {
                    menuLoader.toggleOpened(item.subitems)
                    return
                }

                Qt.callLater(root.playbackModel.handleMenuItem, item.id)
            }

            StyledMenuLoader {
                id: menuLoader

                onHandleMenuItem: function(itemId) {
                    root.playbackModel.handleMenuItem(itemId)
                }
            }
        }
    }

    SeparatorLine {
        id: buttonsSeparator

        anchors.left: buttonsListView.right
        anchors.leftMargin: 6
        anchors.topMargin: 2
        anchors.bottomMargin: 2

        orientation: Qt.Vertical
        visible: !root.floating && !root.compactMode
    }

    TimeInputField {
        id: timeField

        anchors.left: buttonsSeparator.right
        anchors.leftMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 1 // for nicer visual alignment

        //! NOTE: explicit width prevents the content from jumping around
        // when a score is being played
        // See: https://github.com/musescore/MuseScore/issues/9633
        width: 64
        visible: !root.compactMode

        maxTime: root.playbackModel.maxPlayTime
        maxMillisecondsNumber: 9
        time: root.playbackModel.playTime

        navigationPanel: root.navPanel
        navigationOrderStart: buttonsListView.navigationOrderEnd + 1

        onTimeEdited: function(newTime) {
            root.playbackModel.playTime = newTime
        }
    }

    MeasureAndBeatFields {
        id: measureAndBeatFields

        anchors.left: timeField.right
        anchors.leftMargin: 6
        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: 1 // for nicer visual alignment

        measureNumber: root.playbackModel.measureNumber
        maxMeasureNumber: root.playbackModel.maxMeasureNumber
        beatNumber: root.playbackModel.beatNumber
        maxBeatNumber: root.playbackModel.maxBeatNumber

        font: timeField.font
        visible: !root.compactMode

        navigationPanel: root.navPanel
        navigationOrderStart: timeField.navigationOrderEnd + 1

        onMeasureNumberEdited: function(newValue) {
            root.playbackModel.measureNumber = newValue
        }

        onBeatNumberEdited: function(newValue) {
            root.playbackModel.beatNumber = newValue
        }
    }

    Loader {
        id: tempoLoader

        anchors.left: root.compactMode ? buttonsListView.right : measureAndBeatFields.right
        anchors.leftMargin: root.compactMode ? 8 : 6

        readonly property int navigationOrderEnd: item?.navigation?.order ?? measureAndBeatFields.navigationOrderEnd
        visible: true

        // Fixed width prevents items from jumping around; but we
        // scale it according to the font size to prevent clipping
        readonly property real tempoViewWidth: 5 * ui.theme.bodyFont.pixelSize

        sourceComponent: root.floating ? tempoViewComponent : tempoButtonComponent

        Component {
            id: tempoViewComponent

            Item {
                implicitWidth: tempoLoader.tempoViewWidth
                implicitHeight: root.height

                TempoView {
                    id: tempoView
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.verticalCenterOffset: 1 // for nicer visual alignment

                    noteSymbol: root.playbackModel.tempo.noteSymbol
                    tempoValue: root.playbackModel.tempo.value

                    noteSymbolFont.pixelSize: ui.theme.iconsFont.pixelSize
                    tempoValueFont: timeField.font
                }
            }
        }

        Component {
            id: tempoButtonComponent

            PopupButton {
                id: playbackSpeedButton

                implicitWidth: tempoLoader.tempoViewWidth
                implicitHeight: root.height

                transparent: !root.isPopupOpened

                toolTipTitle: "速度"

                navigation.panel: root.navPanel
                navigation.order: measureAndBeatFields.navigationOrderEnd + 1

                contentItem: root.compactMode ? compactTempoContent : tempoContent

                property PlaybackToolBarModel playbackModel: root.playbackModel

                popupComponent: PlaybackSpeedPopup {
                    playbackModel: playbackSpeedButton.playbackModel
                }

                Component {
                    id: tempoContent

                    TempoView {
                        anchors.centerIn: parent
                        anchors.verticalCenterOffset: 1 // for nicer visual alignment

                        noteSymbol: root.playbackModel.tempo.noteSymbol
                        tempoValue: root.playbackModel.tempo.value
                        textColor: ui.theme.fontPrimaryColor

                        noteSymbolFont.pixelSize: ui.theme.iconsFont.pixelSize
                        tempoValueFont: timeField.font
                    }
                }

                Component {
                    id: compactTempoContent

                    StyledTextLabel {
                        text: "BPM " + root.playbackModel.tempo.value
                        color: "#f7ede4"
                        font: Qt.font(Object.assign({}, ui.theme.bodyBoldFont, {
                            family: "Noto Sans CJK SC"
                        }))
                        textFormat: Text.PlainText
                        wrapMode: Text.NoWrap
                    }
                }
            }
        }
    }

    SeparatorLine {
        id: endSeparator
        anchors.left: tempoLoader.right
        anchors.leftMargin: 6
        anchors.topMargin: 2
        anchors.bottomMargin: 2

        orientation: Qt.Vertical
        visible: !root.floating && !root.compactMode
    }
}
