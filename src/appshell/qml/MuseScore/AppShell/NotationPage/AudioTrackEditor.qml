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
    property string bpmInput: ""
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
                text: qsTrc("project", "Accompaniment track")
                font: ui.theme.bodyBoldFont
            }

            FlatButton {
                text: "-"
                enabled: audioModel.hasTrack
                onClicked: timeline.zoomOut()
            }

            FlatButton {
                text: "+"
                enabled: audioModel.hasTrack
                onClicked: timeline.zoomIn()
            }

            FlatButton {
                text: qsTrc("project", "Split")
                enabled: audioModel.hasTrack
                onClicked: audioModel.splitClip(0, audioModel.playbackPosition)
            }

            FlatButton {
                text: qsTrc("project", "Delete clip")
                enabled: audioModel.hasTrack
                onClicked: audioModel.removeClip(0)
            }

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
            Layout.preferredHeight: 128

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

                function clampView() {
                    viewStart = Math.max(0, Math.min(timeRange - viewDuration, viewStart))
                }

                function zoomIn() {
                    var center = viewStart + viewDuration / 2
                    viewDuration = Math.max(0.1, viewDuration / 1.5)
                    viewStart = Math.max(0, Math.min(timeRange - viewDuration, center - viewDuration / 2))
                }

                function zoomOut() {
                    var center = viewStart + viewDuration / 2
                    viewDuration = Math.min(timeRange, viewDuration * 1.5)
                    viewStart = Math.max(0, Math.min(timeRange - viewDuration, center - viewDuration / 2))
                }

                Canvas {
                    id: rulerCanvas

                    anchors.top: parent.top
                    width: parent.width
                    height: 22

                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        ctx.strokeStyle = "#7a7a7a"
                        ctx.fillStyle = "#b7b7b7"
                        ctx.font = "10px sans-serif"

                        var step = timeline.viewDuration > 30 ? 10 : (timeline.viewDuration > 10 ? 5 : 1)
                        var subStep = step / 5
                        var first = Math.floor(timeline.viewStart / step) * step

                        // Minor ticks
                        var firstMinor = Math.floor(timeline.viewStart / subStep) * subStep
                        for (var ms = firstMinor; ms <= timeline.viewStart + timeline.viewDuration; ms += subStep) {
                            var mx = (ms - timeline.viewStart) * timeline.pxPerSec
                            ctx.beginPath()
                            ctx.moveTo(mx, height - 3)
                            ctx.lineTo(mx, height)
                            ctx.stroke()
                        }

                        // Major ticks and labels
                        for (var s = first; s <= timeline.viewStart + timeline.viewDuration; s += step) {
                            var x = (s - timeline.viewStart) * timeline.pxPerSec
                            ctx.beginPath()
                            ctx.moveTo(x, height - 7)
                            ctx.lineTo(x, height)
                            ctx.stroke()
                            ctx.fillText(s + "s", x + 2, height - 9)
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

                        var dur = audioModel.duration > 0 ? audioModel.duration : timeRange
                        var clipStart = audioModel.clipStart
                        var clipEnd = audioModel.clipEnd > 0 ? audioModel.clipEnd : dur

                        // Clip body
                        var clipX = (audioModel.startOffset - timeline.viewStart) * timeline.pxPerSec
                        var clipW = (clipEnd - clipStart) * timeline.pxPerSec
                        if (clipW < 2) clipW = 2

                        ctx.fillStyle = root.clipColor
                        ctx.strokeStyle = root.clipBorder
                        ctx.lineWidth = 1
                        var clipY = 6
                        var clipH = height - 12
                        ctx.fillRect(clipX, clipY, clipW, clipH)
                        ctx.strokeRect(clipX + 0.5, clipY + 0.5, clipW - 1, clipH - 1)

                        // Clip title
                        ctx.fillStyle = "#ffffff"
                        ctx.font = "11px sans-serif"
                        ctx.fillText(qsTrc("project", "Audio"), clipX + 8, clipY + 14)

                        // Waveform inside the clip
                        var peaks = audioModel.waveformPeaks
                        if (peaks && peaks.length > 0) {
                            var n = peaks.length
                            var mid = clipY + clipH / 2
                            var firstIdx = Math.max(0, Math.floor(clipStart / dur * n))
                            var lastIdx = Math.min(n, Math.ceil(clipEnd / dur * n))

                            for (var i = firstIdx; i < lastIdx; ++i) {
                                var t = i / n * dur
                                var x = clipX + (t - clipStart) * timeline.pxPerSec
                                var barWidth = Math.max(1, timeline.pxPerSec * (dur / n) - 1)
                                var amp = Math.max(1, peaks[i] * (clipH / 2 - 8))
                                ctx.fillStyle = root.waveActive
                                ctx.fillRect(x, mid - amp, barWidth, amp * 2)
                            }
                        } else {
                            ctx.fillStyle = root.waveInactive
                            ctx.fillRect(clipX + 4, clipY + clipH / 2 - 1, Math.max(0, clipW - 8), 2)
                        }

                        // Out-of-clip waveform hint
                        if (peaks && peaks.length > 0) {
                            var n2 = peaks.length
                            var viewEnd = timeline.viewStart + timeline.viewDuration
                            var vFirst = Math.max(0, Math.floor(timeline.viewStart / dur * n2))
                            var vLast = Math.min(n2, Math.ceil(viewEnd / dur * n2))
                            for (var j = vFirst; j < vLast; ++j) {
                                var tt = j / n2 * dur
                                if (tt >= clipStart && tt <= clipEnd) continue
                                var xx = (tt - timeline.viewStart) * timeline.pxPerSec
                                var bw = Math.max(1, timeline.pxPerSec * (dur / n2) - 1)
                                var amp2 = Math.max(1, peaks[j] * (clipH / 2 - 8))
                                ctx.fillStyle = root.waveInactive
                                ctx.fillRect(xx, clipY + clipH / 2 - amp2, bw, amp2 * 2)
                            }
                        }
                    }

                    Connections {
                        target: audioModel
                        function onWaveformPeaksChanged() { waveCanvas.requestPaint() }
                        function onClipStartChanged() { waveCanvas.requestPaint() }
                        function onClipEndChanged() { waveCanvas.requestPaint() }
                        function onStartOffsetChanged() { waveCanvas.requestPaint() }
                    }

                    MouseArea {
                        anchors.fill: parent

                        function seekAt(mouseX) {
                            var t = timeline.viewStart + mouseX / timeline.pxPerSec
                            audioModel.seek(Math.max(0, t))
                        }

                        onClicked: function(mouse) {
                            seekAt(mouse.x)
                        }

                        onPositionChanged: function(mouse) {
                            if (pressed) {
                                seekAt(mouse.x)
                            }
                        }
                    }
                }

                // Draggable clip body (moves the clip's start offset)
                Rectangle {
                    id: clipDragArea

                    x: (audioModel.startOffset - timeline.viewStart) * timeline.pxPerSec
                    y: rulerCanvas.height + 6
                    height: timeline.height - rulerCanvas.height - 12
                    width: Math.max(10, ((audioModel.clipEnd > 0 ? audioModel.clipEnd : timeRange) - audioModel.clipStart) * timeline.pxPerSec)
                    color: "transparent"
                    visible: audioModel.hasTrack

                    Connections {
                        target: audioModel
                        function onStartOffsetChanged() {
                            clipDragArea.x = (audioModel.startOffset - timeline.viewStart) * timeline.pxPerSec
                        }
                        function onClipStartChanged() {
                            clipDragArea.width = Math.max(10, ((audioModel.clipEnd > 0 ? audioModel.clipEnd : timeRange) - audioModel.clipStart) * timeline.pxPerSec)
                        }
                        function onClipEndChanged() {
                            clipDragArea.width = Math.max(10, ((audioModel.clipEnd > 0 ? audioModel.clipEnd : timeRange) - audioModel.clipStart) * timeline.pxPerSec)
                        }
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
                            audioModel.moveClip(0, Math.max(0, t))
                        }

                        onReleased: {
                            audioModel.apply()
                        }
                    }
                }

                // Playhead
                Rectangle {
                    id: playhead

                    x: (audioModel.playbackPosition - timeline.viewStart) * timeline.pxPerSec
                    y: 0
                    width: 1
                    height: timeline.height
                    color: root.playheadColor
                    visible: audioModel.playbackPosition >= 0 && audioModel.hasTrack

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
                        anchors.bottom: parent.bottom
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
                            playhead.x = (audioModel.playbackPosition - timeline.viewStart) * timeline.pxPerSec
                            playheadTime.text = root.formatTime(audioModel.playbackPosition)
                        }
                    }
                }

                // Clip start crop handle
                Rectangle {
                    id: clipStartHandle

                    x: (audioModel.startOffset - timeline.viewStart) * timeline.pxPerSec
                    y: rulerCanvas.height + 6
                    width: 10
                    height: timeline.height - rulerCanvas.height - 12
                    color: root.clipBorder
                    radius: 2

                    Connections {
                        target: audioModel
                        function onClipStartChanged() { clipStartHandle.x = (audioModel.startOffset - timeline.viewStart) * timeline.pxPerSec }
                        function onStartOffsetChanged() { clipStartHandle.x = (audioModel.startOffset - timeline.viewStart) * timeline.pxPerSec }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.SizeHorCursor
                        drag.target: clipStartHandle
                        drag.axis: Drag.XAxis
                        drag.minimumX: 0
                        drag.maximumX: clipEndHandle.x - clipStartHandle.width

                        onPositionChanged: {
                            var t = timeline.viewStart + clipStartHandle.x / timeline.pxPerSec
                            audioModel.setClipStart(audioModel.snapToBeat(Math.max(0, t)))
                        }
                        onReleased: audioModel.apply()
                    }
                }

                // Clip end crop handle
                Rectangle {
                    id: clipEndHandle

                    x: ((audioModel.startOffset + (audioModel.clipEnd > 0 ? audioModel.clipEnd : timeRange) - audioModel.clipStart) - timeline.viewStart) * timeline.pxPerSec
                    y: rulerCanvas.height + 6
                    width: 10
                    height: timeline.height - rulerCanvas.height - 12
                    color: root.clipBorder
                    radius: 2

                    Connections {
                        target: audioModel
                        function onClipEndChanged() {
                            var dur = audioModel.duration > 0 ? audioModel.duration : timeRange
                            clipEndHandle.x = (audioModel.startOffset + (audioModel.clipEnd > 0 ? audioModel.clipEnd : dur) - audioModel.clipStart - timeline.viewStart) * timeline.pxPerSec
                        }
                        function onStartOffsetChanged() {
                            var dur = audioModel.duration > 0 ? audioModel.duration : timeRange
                            clipEndHandle.x = (audioModel.startOffset + (audioModel.clipEnd > 0 ? audioModel.clipEnd : dur) - audioModel.clipStart - timeline.viewStart) * timeline.pxPerSec
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
                            var t = timeline.viewStart + clipEndHandle.x / timeline.pxPerSec + audioModel.clipStart - audioModel.startOffset
                            audioModel.setClipEnd(audioModel.snapToBeat(Math.min(timeRange, t)))
                        }
                        onReleased: audioModel.apply()
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
                    onTextChanged: function(newText) {
                        bpmInput = newText
                    }
                }
                FlatButton {
                    text: qsTrc("project", "Tap")
                    onClicked: audioModel.tapTempo()
                }
                FlatButton {
                    text: qsTrc("project", "Apply")
                    onClicked: {
                        var v = parseFloat(bpmInput)
                        if (!isNaN(v) && v > 0) {
                            audioModel.setBpm(v)
                        }
                    }
                }
                StyledTextLabel {
                    text: qsTrc("project", "Measured") + " " + audioModel.measuredBpm.toFixed(3)
                }
                StyledTextLabel {
                    text: audioModel.speed.toFixed(3) + "×"
                }
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
