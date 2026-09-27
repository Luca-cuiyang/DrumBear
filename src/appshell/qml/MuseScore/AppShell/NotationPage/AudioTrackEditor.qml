/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2026 DB Score contributors
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
import DBScore.Project

Item {
    id: root

    property NavigationSection navigationSection: null
    property int contentNavigationPanelOrderStart: 0

    required property AudioTrackSettingsModel audioModel

    property double timeRange: audioModel.duration > 0 ? audioModel.duration : 600

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 8

        RowLayout {
            Layout.fillWidth: true

            StyledTextLabel {
                text: qsTrc("project", "Accompaniment track")
                font: ui.theme.bodyBoldFont
            }

            Item { Layout.fillWidth: true }

            FlatButton {
                text: qsTrc("project", "Choose audio track")

                onClicked: {
                    audioModel.chooseFile()
                }
            }

            FlatButton {
                text: qsTrc("project", "Remove")
                enabled: audioModel.hasTrack

                onClicked: {
                    audioModel.remove()
                }
            }
        }

        Item {
            id: timeline

            Layout.fillWidth: true
            Layout.preferredHeight: 112

            clip: true

            property double pxPerSec: width / timeRange

            Canvas {
                id: rulerCanvas

                anchors.top: parent.top
                width: parent.width
                height: 20

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.fillStyle = "#6f6f6f"
                    ctx.strokeStyle = "#6f6f6f"
                    ctx.font = "10px sans-serif"

                    var step = timeRange > 30 ? 10 : (timeRange > 10 ? 5 : 1)
                    for (var s = 0; s <= timeRange; s += step) {
                        var x = s * timeline.pxPerSec
                        ctx.beginPath()
                        ctx.moveTo(x, height - 6)
                        ctx.lineTo(x, height)
                        ctx.stroke()
                        ctx.fillText(s + "s", x + 2, height - 8)
                    }
                }
            }

            Canvas {
                id: waveCanvas

                anchors.top: rulerCanvas.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)

                    var mid = height / 2
                    var peaks = audioModel.waveformPeaks
                    if (!peaks || peaks.length === 0) {
                        ctx.fillStyle = "#4d4d4d"
                        ctx.fillRect(0, mid - 1, width, 2)
                        return
                    }

                    var n = peaks.length
                    var barWidth = Math.max(1, width / n)
                    var clipStartFrac = audioModel.duration > 0 ? audioModel.clipStart / audioModel.duration : 0
                    var clipEndFrac = audioModel.duration > 0
                                      ? (audioModel.clipEnd > 0 ? audioModel.clipEnd / audioModel.duration : 1)
                                      : 1

                    for (var i = 0; i < n; ++i) {
                        var frac = i / n
                        var amp = Math.max(1, peaks[i] * mid)
                        ctx.fillStyle = (frac >= clipStartFrac && frac <= clipEndFrac) ? "#2f80ed" : "#6f6f6f"
                        ctx.fillRect(i * barWidth, mid - amp, Math.max(1, barWidth - 1), amp * 2)
                    }
                }

                Connections {
                    target: audioModel
                    function onWaveformPeaksChanged() { waveCanvas.requestPaint() }
                    function onClipStartChanged() { waveCanvas.requestPaint() }
                    function onClipEndChanged() { waveCanvas.requestPaint() }
                }
            }

            Rectangle {
                id: playhead

                x: audioModel.playbackPosition * timeline.pxPerSec
                y: rulerCanvas.height
                width: 1
                height: waveCanvas.height
                color: "#ff5252"
                visible: audioModel.playbackPosition >= 0 && audioModel.hasTrack

                Connections {
                    target: audioModel
                    function onPlaybackPositionChanged() {
                        playhead.x = audioModel.playbackPosition * timeline.pxPerSec
                    }
                }
            }

            Rectangle {
                id: clipStartHandle

                x: 0
                y: rulerCanvas.height
                width: 8
                height: waveCanvas.height
                color: "#2f80ed"

                Connections {
                    target: audioModel
                    function onClipStartChanged() {
                        clipStartHandle.x = audioModel.clipStart * timeline.pxPerSec
                    }
                    function onDurationChanged() {
                        clipStartHandle.x = audioModel.clipStart * timeline.pxPerSec
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.SizeHorCursor
                    drag.target: clipStartHandle
                    drag.axis: Drag.XAxis
                    drag.minimumX: 0
                    drag.maximumX: clipEndHandle.x - clipStartHandle.width

                    onPositionChanged: {
                        audioModel.setClipStart(clipStartHandle.x / timeline.pxPerSec)
                    }

                    onReleased: {
                        audioModel.apply()
                    }
                }
            }

            Rectangle {
                id: clipEndHandle

                x: timeline.width
                y: rulerCanvas.height
                width: 8
                height: waveCanvas.height
                color: "#2f80ed"

                Connections {
                    target: audioModel
                    function onClipEndChanged() {
                        clipEndHandle.x = (audioModel.clipEnd > 0 ? audioModel.clipEnd : timeRange) * timeline.pxPerSec
                    }
                    function onDurationChanged() {
                        clipEndHandle.x = (audioModel.clipEnd > 0 ? audioModel.clipEnd : timeRange) * timeline.pxPerSec
                    }
                    function onHasTrackChanged() {
                        clipEndHandle.x = (audioModel.clipEnd > 0 ? audioModel.clipEnd : timeRange) * timeline.pxPerSec
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.SizeHorCursor
                    drag.target: clipEndHandle
                    drag.axis: Drag.XAxis
                    drag.minimumX: clipStartHandle.x + clipStartHandle.width
                    drag.maximumX: timeline.width - clipEndHandle.width

                    onPositionChanged: {
                        audioModel.setClipEnd(clipEndHandle.x / timeline.pxPerSec)
                    }

                    onReleased: {
                        audioModel.apply()
                    }
                }
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 16
            rowSpacing: 6

            StyledTextLabel { text: qsTrc("project", "Start offset") }
            RowLayout {
                Layout.fillWidth: true
                StyledSlider {
                    Layout.fillWidth: true
                    value: audioModel.startOffset
                    from: 0
                    to: timeRange
                    stepSize: 0.01
                    onMoved: { audioModel.setStartOffset(value); audioModel.apply() }
                }
                StyledTextLabel { text: audioModel.startOffset.toFixed(2) + " s" }
            }

            StyledTextLabel { text: qsTrc("project", "Speed") }
            RowLayout {
                Layout.fillWidth: true
                StyledSlider {
                    Layout.fillWidth: true
                    value: audioModel.speed
                    from: 0.25
                    to: 2.0
                    stepSize: 0.05
                    onMoved: { audioModel.setSpeed(value); audioModel.apply() }
                }
                StyledTextLabel { text: audioModel.speed.toFixed(2) + "×" }
            }

            StyledTextLabel { text: qsTrc("project", "Volume") }
            RowLayout {
                Layout.fillWidth: true
                StyledSlider {
                    Layout.fillWidth: true
                    value: audioModel.volumeDb
                    from: -60
                    to: 12
                    stepSize: 0.5
                    onMoved: { audioModel.setVolumeDb(value); audioModel.apply() }
                }
                StyledTextLabel { text: audioModel.volumeDb.toFixed(1) + " dB" }
            }
        }

        CheckBox {
            text: qsTrc("project", "Mute")
            checked: audioModel.muted
            onCheckedChanged: { audioModel.setMuted(checked); audioModel.apply() }
        }
    }
}
