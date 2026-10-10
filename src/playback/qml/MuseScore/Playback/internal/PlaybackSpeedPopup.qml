/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2023 MuseScore Limited and others
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
import QtQuick.Layouts

import Muse.Ui
import Muse.UiComponents

import DBScore.Playback

StyledPopupView {
    id: root

    property PlaybackToolBarModel playbackModel: null

    property var cursorColors: ["#F57C00", "#0065BF", "#E53935", "#00BCD4", "#E91E63", "#333333"]

    function isCursorColorSelected(hex) {
        if (!root.playbackModel) {
            return false
        }
        return root.playbackModel.playbackCursorColor.toString().toUpperCase() === hex
    }

    contentWidth: contentColumn.implicitWidth
    contentHeight: contentColumn.implicitHeight

    NavigationPanel {
        id: navPanel
        name: "PlaybackSpeedPopup"
        section: root.navigationSection
        accessible.name: "播放设置"
    }

    ColumnLayout {
        id: contentColumn
        spacing: 8

        StyledTextLabel {
            Layout.fillWidth: true
            text: "速度"
            horizontalAlignment: Text.AlignLeft
        }

        RowLayout {
            spacing: 12

            IncrementalPropertyControl {
                Layout.preferredWidth: 76
                currentValue: root.playbackModel.tempoMultiplier * 100

                maxValue: 300
                minValue: 10
                step: 5
                measureUnitsSymbol: "%"
                decimals: 0

                navigation.panel: navPanel
                navigation.accessible.name: "速度"

                onValueEdited: function(newValue) {
                    root.playbackModel.tempoMultiplier = newValue / 100
                }
            }

            StyledSlider {
                Layout.preferredWidth: 200
                Layout.preferredHeight: 30

                value: root.playbackModel.tempoMultiplier
                from: 0.1
                to: 3.0
                stepSize: 0.05

                fillBackground: false

                onMoved: {
                    root.playbackModel.tempoMultiplier = value
                }
            }
        }

        StyledTextLabel {
            Layout.fillWidth: true
            text: "播放指针"
            horizontalAlignment: Text.AlignLeft
        }

        RowLayout {
            spacing: 8

            StyledTextLabel { text: "颜色" }

            Repeater {
                model: root.cursorColors
                Rectangle {
                    width: 16
                    height: 16
                    radius: 3
                    color: modelData
                    border.width: root.isCursorColorSelected(modelData) ? 2 : 1
                    border.color: root.isCursorColorSelected(modelData) ? "#333333" : "#C9CFCA"

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.playbackModel.setPlaybackCursorColor(modelData)
                    }
                }
            }
        }

        RowLayout {
            spacing: 8

            StyledTextLabel { text: "长短" }
            StyledSlider {
                Layout.preferredWidth: 160
                from: 0.2
                to: 1.0
                stepSize: 0.01
                value: root.playbackModel.playbackCursorLength
                onMoved: root.playbackModel.setPlaybackCursorLength(value)
            }
        }

        RowLayout {
            spacing: 8

            StyledTextLabel { text: "粗细" }
            StyledSlider {
                Layout.preferredWidth: 160
                from: 0.15
                to: 1.0
                stepSize: 0.01
                value: root.playbackModel.playbackCursorThickness
                onMoved: root.playbackModel.setPlaybackCursorThickness(value)
            }
        }

        RowLayout {
            spacing: 8

            StyledTextLabel { text: "透明度" }
            StyledSlider {
                Layout.preferredWidth: 160
                from: 0.15
                to: 1.0
                stepSize: 0.01
                value: root.playbackModel.playbackCursorOpacity
                onMoved: root.playbackModel.setPlaybackCursorOpacity(value)
            }
        }
    }
}
