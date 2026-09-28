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

    property string bpmInput: ""

    property double audioDuration: audioModel.duration > 0 ? audioModel.duration : 0
    property double scoreDuration: audioModel.scoreDuration > 0 ? audioModel.scoreDuration : 0
    property double contentDuration: Math.max(audioDuration, scoreDuration)
    property double padding: 30
    property double timeRange: contentDuration + padding * 2

    property color timelineBg: "#1f1f1f"
    property color clipColor: "#3a3a3a"
    property color clipBorder: "#2f80ed"
    property color accent: "#2f80ed"
    property color waveActive: "#7db8ff"
    property color waveInactive: "#5a5a5a"
    property color playheadColor: "#ff5252"

    function formatTime(secs) {
        var s = Math.max(0, secs)
        var m = Math.floor(s / 60)
        var sec = (s % 60).toFixed(2)
        return (m < 10 ? "0" : "") + m + ":" + (sec < 10 ? "0" : "") + sec
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        RowLayout {
            Layout.fillWidth: true

            StyledTextLabel {
                text: qsTrc("project", "Audio alignment")
                font: ui.theme.bodyBoldFont
            }

            FlatButton { text: "-"; onClicked: timeline.zoomOut() }
            FlatButton { text: "+"; onClicked: timeline.zoomIn() }

            Item { Layout.fillWidth: true }

            FlatButton {
                text: qsTrc("project", "Choose audio track")
                onClicked: audioModel.chooseFile()
            }

            FlatButton {
                text: qsTrc("project", "Remove")
                enabled: audioModel.hasTrack
                onClicked: audioModel.remove()
            }
        }

        Rectangle {
            id: timelineBg

            Layout.fillWidth: true
            Layout.preferredHeight: 150
            color: timelineBg
            radius: 8
            clip: true

            Item {
                id: timeline

                anchors.fill: parent
                anchors.margins: 8

                property double viewStart: 0
                property double viewDuration: timeRange
                property double pxPerSec: width > 0 ? width / viewDuration : 0

                function zoomIn() {
                    var c = viewStart + viewDuration / 2
                    viewDuration = Math.max(1, viewDuration / 1.5)
                    viewStart = Math.max(0, Math.min(timeRange - viewDuration, c - viewDuration / 2))
                }

                function zoomOut() {
                    var c = viewStart + viewDuration / 2
                    viewDuration = Math.min(timeRange, viewDuration * 1.5)
                    viewStart = Math.max(0, Math.min(timeRange - viewDuration, c - viewDuration / 2))
                }

                Canvas {
                    id: rulerCanvas
                    anchors.top: parent.top
                    width: parent.width
                    height: 24

                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        ctx.strokeStyle = "#7a7a7a"
                        ctx.fillStyle = "#b7b7b7"
                        ctx.font = "10px sans-serif"

                        var step = timeline.viewDuration > 30 ? 10 : (timeline.viewDuration > 10 ? 5 : 1)
                        var subStep = step / 5
                        var firstMinor = Math.floor(timeline.viewStart / subStep) * subStep
                        for (var ms = firstMinor; ms <= timeline.viewStart + timeline.viewDuration; ms += subStep) {
                            var mx = (ms - timeline.viewStart) * timeline.pxPerSec
                            ctx.beginPath()
                            ctx.moveTo(mx, height - 3)
                            ctx.lineTo(mx, height)
                            ctx.stroke()
                        }

                        var first = Math.floor(timeline.viewStart / step) * step
                        for (var s = first; s <= timeline.viewStart + timeline.viewDuration; s += step) {
                            var x = (s - timeline.viewStart) * timeline.pxPerSec
                            ctx.beginPath()
                            ctx.moveTo(x, height - 8)
                            ctx.lineTo(x, height)
                            ctx.stroke()
                            ctx.fillText(s + "s", x + 2, height - 10)
                        }
                    }
                }

                // Score beat grid track
                Rectangle {
                    id: scoreTrack
                    anchors.top: rulerCanvas.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    height: 36
                    color: "#242424"

                    Canvas {
                        id: scoreGridCanvas
                        anchors.fill: parent

                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            if (scoreDuration <= 0) return

                            ctx.strokeStyle = "#4a4a4a"
                            ctx.fillStyle = "#8a8a8a"
                            ctx.font = "9px sans-serif"
                            var step = scoreDuration > 30 ? 5 : (scoreDuration > 10 ? 2 : 1)
                            var start = audioModel.scoreOffset
                            var end = start + scoreDuration
                            for (var s = Math.ceil(start); s <= end; s += step) {
                                var x = (s - timeline.viewStart) * timeline.pxPerSec
                                ctx.beginPath()
                                ctx.moveTo(x, 0)
                                ctx.lineTo(x, height)
                                ctx.stroke()
                                ctx.fillText(s + "s", x + 2, 10)
                            }
                        }
                    }

                    Connections {
                        target: audioModel
                        function onScoreOffsetChanged() { scoreGridCanvas.requestPaint() }
                        function onScoreDurationChanged() { scoreGridCanvas.requestPaint() }
                    }

                    // Drag to move the whole score grid
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.OpenHandCursor
                        drag.target: scoreTrack
                        drag.axis: Drag.XAxis
                        drag.minimumX: -timeline.width
                        drag.maximumX: timeline.width
                        onPositionChanged: {
                            var t = timeline.viewStart + scoreTrack.x / timeline.pxPerSec
                            audioModel.setScoreOffset(t)
                        }
                    }
                }

                // Audio waveform track
                Rectangle {
                    id: audioTrack
                    anchors.top: scoreTrack.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    color: "#1b1b1b"

                    Canvas {
                        id: waveCanvas
                        anchors.fill: parent

                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)

                            var dur = audioModel.duration > 0 ? audioModel.duration : 1
                            var clipX = (audioModel.startOffset - timeline.viewStart) * timeline.pxPerSec
                            var clipW = dur * timeline.pxPerSec
                            if (clipW < 2) clipW = 2

                            var clipY = 6
                            var clipH = height - 12
                            ctx.fillStyle = root.clipColor
                            ctx.strokeStyle = root.clipBorder
                            ctx.lineWidth = 1
                            ctx.fillRect(clipX, clipY, clipW, clipH)
                            ctx.strokeRect(clipX + 0.5, clipY + 0.5, clipW - 1, clipH - 1)

                            ctx.fillStyle = "#ffffff"
                            ctx.font = "11px sans-serif"
                            ctx.fillText(qsTrc("project", "Audio"), clipX + 8, clipY + 14)

                            var peaks = audioModel.waveformPeaks
                            if (peaks && peaks.length > 0) {
                                var n = peaks.length
                                var mid = clipY + clipH / 2
                                for (var i = 0; i < n; ++i) {
                                    var t = i / n * dur
                                    var x = clipX + t * timeline.pxPerSec
                                    var bw = Math.max(1, timeline.pxPerSec * (dur / n) - 1)
                                    var amp = Math.max(1, peaks[i] * (clipH / 2 - 8))
                                    ctx.fillStyle = root.waveActive
                                    ctx.fillRect(x, mid - amp, bw, amp * 2)
                                }
                            } else {
                                ctx.fillStyle = root.waveInactive
                                ctx.fillRect(clipX + 4, clipY + clipH / 2 - 1, Math.max(0, clipW - 8), 2)
                            }
                        }

                        Connections {
                            target: audioModel
                            function onWaveformPeaksChanged() { waveCanvas.requestPaint() }
                            function onStartOffsetChanged() { waveCanvas.requestPaint() }
                            function onDurationChanged() { waveCanvas.requestPaint() }
                        }

                        // Scrub / seek
                        MouseArea {
                            anchors.fill: parent
                            function seekAt(mouseX) {
                                var t = timeline.viewStart + mouseX / timeline.pxPerSec
                                audioModel.seek(Math.max(0, t))
                            }
                            onClicked: function(mouse) { seekAt(mouse.x) }
                            onPositionChanged: function(mouse) { if (pressed) seekAt(mouse.x) }
                        }
                    }

                    // Drag the audio clip to move it
                    Rectangle {
                        id: clipDragArea
                        x: (audioModel.startOffset - timeline.viewStart) * timeline.pxPerSec
                        y: 6
                        width: Math.max(10, audioModel.duration * timeline.pxPerSec)
                        height: parent.height - 12
                        color: "transparent"
                        visible: audioModel.hasTrack

                        Connections {
                            target: audioModel
                            function onStartOffsetChanged() { clipDragArea.x = (audioModel.startOffset - timeline.viewStart) * timeline.pxPerSec }
                            function onDurationChanged() { clipDragArea.width = Math.max(10, audioModel.duration * timeline.pxPerSec) }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.OpenHandCursor
                            drag.target: clipDragArea
                            drag.axis: Drag.XAxis
                            drag.minimumX: 0
                            drag.maximumX: timeline.width - clipDragArea.width
                            onPositionChanged: {
                                var t = timeline.viewStart + clipDragArea.x / timeline.pxPerSec
                                audioModel.setStartOffset(Math.max(0, t))
                                audioModel.apply()
                            }
                            onReleased: audioModel.apply()
                        }
                    }
                }

                // Playhead spanning ruler + both tracks
                Rectangle {
                    id: playhead
                    x: (audioModel.playbackPosition - timeline.viewStart) * timeline.pxPerSec
                    y: 0
                    width: 1
                    height: timeline.height
                    color: root.playheadColor
                    visible: audioModel.playbackPosition >= 0

                    Text {
                        id: playheadTime
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.top
                        text: root.formatTime(audioModel.playbackPosition)
                        color: root.playheadColor
                        font.pixelSize: 10
                    }

                    Canvas {
                        id: playheadHandle
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.top: parent.top
                        width: 12
                        height: 12
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            ctx.fillStyle = root.playheadColor
                            ctx.beginPath()
                            ctx.moveTo(0, 0)
                            ctx.lineTo(width, 0)
                            ctx.lineTo(width / 2, height)
                            ctx.closePath()
                            ctx.fill()
                        }
                    }

                    Connections {
                        target: audioModel
                        function onPlaybackPositionChanged() {
                            var p = audioModel.playbackPosition
                            if (p > timeline.viewStart + timeline.viewDuration * 0.85) {
                                timeline.viewStart = Math.min(timeRange - timeline.viewDuration, p - timeline.viewDuration * 0.85)
                            } else if (p < timeline.viewStart) {
                                timeline.viewStart = Math.max(0, p)
                            }
                            rulerCanvas.requestPaint()
                            waveCanvas.requestPaint()
                        }
                    }
                }
            }
        }

        StyledSlider {
            Layout.fillWidth: true
            value: timeline.viewStart
            from: 0
            to: Math.max(0, timeRange - timeline.viewDuration)
            stepSize: 0.01
            onMoved: {
                timeline.viewStart = value
                rulerCanvas.requestPaint()
                waveCanvas.requestPaint()
            }
        }

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 16
            rowSpacing: 6

            StyledTextLabel { text: qsTrc("project", "BPM") }
            RowLayout {
                Layout.fillWidth: true
                TextInputField {
                    Layout.preferredWidth: 120
                    currentText: bpmInput
                    onTextChanged: function(newText) { bpmInput = newText }
                }
                FlatButton { text: qsTrc("project", "Tap"); onClicked: audioModel.tapTempo() }
                FlatButton {
                    text: qsTrc("project", "Apply")
                    onClicked: {
                        var v = parseFloat(bpmInput)
                        if (!isNaN(v) && v > 0) audioModel.setBpm(v)
                    }
                }
                StyledTextLabel { text: qsTrc("project", "Measured") + " " + audioModel.measuredBpm.toFixed(3) }
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
