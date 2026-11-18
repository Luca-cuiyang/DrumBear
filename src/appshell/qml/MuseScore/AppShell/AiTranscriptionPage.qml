/*
 * SPDX-License-Identifier: GPL-3.0-only
 */

pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

import Muse.Dock
import Muse.Interactive
import Muse.Ui
import Muse.UiComponents

import DBScore.AppShell

DockPage {
    id: root

    objectName: "AiTranscription"
    uri: "dbscore://ai-transcription"

    central: mainContent

    property string mode: "image"
    property string midiPath: ""
    property var imagePaths: []
    property string outputPath: ""
    property string imageTitle: ""
    property int imageTempo: 120
    property int leadingMeasures: 0
    property bool diagnosticsVisible: false
    property int reviewPageIndex: 0

    readonly property bool imageMode: mode === "image"
    readonly property var currentReport: transcription.report
    readonly property bool strictValid: currentReport.valid === true

    function pathText(value) {
        if (!value)
            return ""
        if (typeof value.toLocalFile === "function")
            return value.toLocalFile()
        var text = value.toString()
        if (text.startsWith("file://"))
            return decodeURIComponent(text.substring(text.indexOf("file://") + 7))
        return text
    }

    function fileName(path) {
        var value = pathText(path)
        var index = Math.max(value.lastIndexOf("/"), value.lastIndexOf("\\"))
        return index >= 0 ? value.substring(index + 1) : value
    }

    function suggestedOutput(path) {
        var value = pathText(path)
        value = value.replace(/\.(midi?|png|jpe?g|tiff?|bmp|webp|pdf)$/i, "")
        return value + "-鼓.db"
    }

    function suggestedTitle(path) {
        return fileName(path).replace(/\.(midi?|png|jpe?g|tiff?|bmp|webp|pdf)$/i, "")
    }

    function selectMode(value) {
        if (transcription.busy)
            return
        mode = value
        transcription.reset()
    }

    function fileUrl(path) {
        if (!path)
            return ""
        return path.startsWith("/") ? "file://" + encodeURI(path) : path
    }

    function startConversion() {
        if (transcription.busy)
            return
        if (imageMode) {
            if (imagePaths.length === 0) {
                transcription.showError(qsTr("请先选择鼓谱图片或 PDF"))
                return
            }
            transcription.startImages(
                imagePaths,
                outputPath,
                imageTitle,
                imageTempo
            )
            return
        }
        if (!midiPath) {
            transcription.showError(qsTr("请先选择 MIDI 文件"))
            return
        }
        transcription.startMidi(
            midiPath,
            outputPath,
            gridCombo.currentValue,
            bpmMode.currentValue,
            bpmField.text,
            shiftCombo.currentValue,
            leadingMeasures
        )
    }

    NavigationSection {
        id: navSec
        name: "AiTranscription"
        enabled: root.enabled && root.visible
        order: 3
    }

    AiTranscriptionModel {
        id: transcription
    }

    FileDialog {
        id: midiDialog
        title: qsTr("选择 MIDI 文件")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("MIDI 文件 (*.mid *.midi)")]
        onAccepted: {
            root.midiPath = root.pathText(currentFile)
            root.outputPath = root.suggestedOutput(root.midiPath)
            root.imageTitle = root.suggestedTitle(root.midiPath)
            transcription.reset()
        }
    }

    FileDialog {
        id: imageDialog
        title: qsTr("选择鼓谱图片或 PDF")
        fileMode: FileDialog.OpenFiles
        nameFilters: [qsTr("鼓谱图片或 PDF (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp *.pdf)")]
        onAccepted: {
            var paths = []
            var urls = fileUrls || []
            for (var i = 0; i < urls.length; ++i)
                paths.push(root.pathText(urls[i]))
            root.imagePaths = paths
            if (paths.length > 0) {
                root.outputPath = root.suggestedOutput(paths[0])
                if (!root.imageTitle)
                    root.imageTitle = root.suggestedTitle(paths[0])
            }
            transcription.reset()
        }
    }

    FileDialog {
        id: outputDialog
        title: qsTr("保存 DB Score 鼓谱")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("DB Score 鼓谱 (*.db)")]
        currentFile: root.outputPath
        onAccepted: root.outputPath = root.pathText(currentFile)
    }

    FolderDialog {
        id: reviewProjectDialog
        title: qsTr("选择 AI转谱复核资料目录")
        onAccepted: transcription.loadReviewProject(currentFolder.toString())
    }

    Component {
        id: mainContent

        Item {

    Rectangle {
        anchors.fill: parent
        color: ui.theme.backgroundSecondaryColor
    }

    Flickable {
        id: scroller
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: contentColumn.height + 72
        boundsBehavior: Flickable.StopAtBounds

        ColumnLayout {
            id: contentColumn
            x: 48
            y: 32
            width: Math.max(1, root.width - 96)
            spacing: 18

            RowLayout {
                Layout.fillWidth: true
                spacing: 14

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5

                    RowLayout {
                        spacing: 10
                        StyledTextLabel {
                            text: qsTr("AI转谱")
                            font: ui.theme.titleBoldFont
                        }
                        Rectangle {
                            implicitWidth: poweredLabel.implicitWidth + 16
                            implicitHeight: 24
                            radius: 7
                            color: "#E8F0FF"
                            StyledTextLabel {
                                id: poweredLabel
                                anchors.centerIn: parent
                                text: "✦ AI POWERED"
                                color: "#2F6EE5"
                                font: ui.theme.bodyBoldFont
                            }
                        }
                    }

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTr("三种架子鼓鼓谱输入方式，统一输出可编辑的 DB Score .db 文件")
                        color: ui.theme.fontSecondaryColor
                        font: ui.theme.bodyFont
                    }
                }

                Rectangle {
                    implicitWidth: localText.implicitWidth + 34
                    implicitHeight: 34
                    radius: 17
                    color: ui.theme.backgroundPrimaryColor
                    border.color: ui.theme.strokeColor

                    Row {
                        anchors.centerIn: parent
                        spacing: 8
                        Rectangle {
                            width: 7
                            height: 7
                            radius: 4
                            color: "#25A66A"
                        }
                        StyledTextLabel {
                            id: localText
                            text: qsTr("本机处理")
                            color: ui.theme.fontSecondaryColor
                            font: ui.theme.bodyFont
                        }
                    }
                }

                FlatButton {
                    text: qsTr("环境检查")
                    onClicked: root.diagnosticsVisible = !root.diagnosticsVisible
                }
            }

            Rectangle {
                Layout.fillWidth: true
                visible: transcription.reviewRequired
                implicitHeight: reviewLayout.implicitHeight + 32
                radius: 14
                color: ui.theme.backgroundPrimaryColor
                border.color: "#E6D9C9"

                ColumnLayout {
                    id: reviewLayout
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTr("逐小节复核")
                            font: ui.theme.titleBoldFont
                        }
                        StyledTextLabel {
                            text: qsTr("已确认 %1 / %2")
                                  .arg(transcription.reviewedMeasureCount)
                                  .arg(transcription.reviewMeasureCount)
                            color: transcription.reviewedMeasureCount === transcription.reviewMeasureCount
                                   ? "#20895A" : "#B96B2D"
                            font: ui.theme.bodyBoldFont
                        }
                        FlatButton {
                            text: qsTr("打开复核资料")
                            onClicked: transcription.revealReviewProject()
                        }
                        FlatButton {
                            text: qsTr("生成正式鼓谱")
                            accentButton: true
                            enabled: !transcription.busy
                                     && transcription.reviewedMeasureCount === transcription.reviewMeasureCount
                            onClicked: transcription.finalizeImageReview()
                        }
                    }

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTr("左侧是原谱，右侧是音符与鼓件识别标记。逐页核对拍位、鼓件、声部和符干方向；确认无误后勾选对应小节。")
                        color: ui.theme.fontSecondaryColor
                        wrapMode: Text.WordWrap
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 360
                            radius: 9
                            color: "#F2F3F5"
                            border.color: ui.theme.strokeColor
                            clip: true

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 0
                                StyledTextLabel {
                                    Layout.fillWidth: true
                                    Layout.margins: 8
                                    text: qsTr("原谱图片")
                                    font: ui.theme.bodyBoldFont
                                }
                                Image {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    fillMode: Image.PreserveAspectFit
                                    source: transcription.reviewPages.length > root.reviewPageIndex
                                            ? root.fileUrl(transcription.reviewPages[root.reviewPageIndex].original)
                                            : ""
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 360
                            radius: 9
                            color: "#F2F3F5"
                            border.color: ui.theme.strokeColor
                            clip: true

                            ColumnLayout {
                                anchors.fill: parent
                                spacing: 0
                                StyledTextLabel {
                                    Layout.fillWidth: true
                                    Layout.margins: 8
                                    text: qsTr("识别标记")
                                    font: ui.theme.bodyBoldFont
                                }
                                Image {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    fillMode: Image.PreserveAspectFit
                                    source: transcription.reviewPages.length > root.reviewPageIndex
                                            ? root.fileUrl(transcription.reviewPages[root.reviewPageIndex].generated)
                                            : ""
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        FlatButton {
                            text: qsTr("上一页")
                            enabled: root.reviewPageIndex > 0
                            onClicked: --root.reviewPageIndex
                        }
                        StyledTextLabel {
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            text: transcription.reviewPages.length > root.reviewPageIndex
                                  ? qsTr("第 %1 / %2 页 · 第 %3–%4 小节")
                                      .arg(root.reviewPageIndex + 1)
                                      .arg(transcription.reviewPages.length)
                                      .arg(transcription.reviewPages[root.reviewPageIndex].firstMeasure)
                                      .arg(transcription.reviewPages[root.reviewPageIndex].lastMeasure)
                                  : ""
                        }
                        FlatButton {
                            text: qsTr("下一页")
                            enabled: root.reviewPageIndex + 1 < transcription.reviewPages.length
                            onClicked: ++root.reviewPageIndex
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 260
                        radius: 9
                        color: ui.theme.backgroundSecondaryColor
                        border.color: ui.theme.strokeColor
                        clip: true

                        ListView {
                            anchors.fill: parent
                            anchors.margins: 8
                            clip: true
                            model: transcription.reviewMeasures
                            spacing: 4

                            delegate: Rectangle {
                                required property var modelData
                                width: ListView.view.width
                                height: 42
                                radius: 6
                                color: modelData.reviewed ? "#F1FAF5"
                                                         : ((modelData.unresolvedCount > 0
                                                             || modelData.reviewReasonCount > 0)
                                                            ? "#FFF8F1" : ui.theme.backgroundPrimaryColor)

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 10
                                    anchors.rightMargin: 10
                                    CheckBox {
                                        checked: modelData.reviewed
                                        onClicked: transcription.setMeasureReviewed(
                                                       modelData.number, !checked)
                                    }
                                    StyledTextLabel {
                                        text: qsTr("第 %1 小节").arg(modelData.number)
                                        font: ui.theme.bodyBoldFont
                                    }
                                    StyledTextLabel {
                                        Layout.fillWidth: true
                                        text: modelData.unresolvedCount > 0
                                              ? qsTr("%1 个记号需要核对").arg(modelData.unresolvedCount)
                                              : (modelData.reviewReasonCount > 0
                                                 ? modelData.reviewReasons.join("；")
                                                 : (modelData.qualityFlagCount > 0
                                                    ? modelData.qualityFlags.join("；")
                                                    : qsTr("自动结构检查无警告")))
                                        color: (modelData.unresolvedCount > 0
                                                || modelData.reviewReasonCount > 0)
                                               ? "#B96B2D" : ui.theme.fontSecondaryColor
                                        elide: Text.ElideRight
                                    }
                                    StyledTextLabel {
                                        text: modelData.reviewed
                                              ? (modelData.autoAccepted
                                                 ? qsTr("自动通过")
                                                 : qsTr("已确认"))
                                              : qsTr("待确认")
                                        color: modelData.reviewed ? "#20895A" : "#B96B2D"
                                    }
                                    FlatButton {
                                        text: qsTr("编辑")
                                        onClicked: transcription.selectReviewMeasure(modelData.number)
                                    }
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        visible: transcription.selectedReviewMeasure > 0
                        implicitHeight: eventEditorColumn.implicitHeight + 22
                        radius: 9
                        color: ui.theme.backgroundSecondaryColor
                        border.color: ui.theme.strokeColor

                        ColumnLayout {
                            id: eventEditorColumn
                            anchors.fill: parent
                            anchors.margins: 11
                            spacing: 8

                            StyledTextLabel {
                                text: qsTr("事件修正 · 第 %1 小节")
                                      .arg(transcription.selectedReviewMeasure)
                                font: ui.theme.bodyBoldFont
                            }
                            Image {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 170
                                visible: transcription.selectedReviewSourceCrop !== ""
                                source: root.fileUrl(
                                            transcription.selectedReviewSourceCrop)
                                fillMode: Image.PreserveAspectFit
                            }
                            Column {
                                Layout.fillWidth: true
                                spacing: 3
                                visible: transcription.selectedReviewVisualErrors.length > 0
                                Repeater {
                                    model: transcription.selectedReviewVisualErrors
                                    StyledTextLabel {
                                        required property string modelData
                                        width: parent.width
                                        text: "• " + modelData
                                        color: "#B4492F"
                                        wrapMode: Text.WordWrap
                                        font: ui.theme.bodyFont
                                    }
                                }
                            }
                            FlatButton {
                                Layout.alignment: Qt.AlignLeft
                                text: qsTr("按拍位重算时值、符尾与符杠")
                                onClicked: transcription.reflowReviewMeasure(
                                               transcription.selectedReviewMeasure)
                            }
                            RowLayout {
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTr("本小节拍数（四分音符为一拍）")
                                    color: ui.theme.fontSecondaryColor
                                }
                                SpinBox {
                                    from: 1
                                    to: 16
                                    value: transcription.selectedReviewMeasureLength
                                    onValueModified: transcription.updateReviewMeasureLength(
                                                          transcription.selectedReviewMeasure,
                                                          value)
                                }
                            }
                            StyledTextLabel {
                                Layout.fillWidth: true
                                text: qsTr("拍位按全音符分数填写，例如 0、1/16、1/8、3/16。鼓件填写 GM 音高，用逗号分隔。")
                                color: ui.theme.fontSecondaryColor
                                wrapMode: Text.WordWrap
                            }

                            ListView {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 190
                                clip: true
                                model: transcription.selectedReviewEvents
                                spacing: 5

                                delegate: RowLayout {
                                    required property var modelData
                                    required property int index
                                    width: ListView.view.width
                                    spacing: 8

                                    StyledTextLabel {
                                        Layout.preferredWidth: 44
                                        text: "#" + (index + 1)
                                        color: ui.theme.fontSecondaryColor
                                    }
                                    TextField {
                                        id: eventTimeField
                                        Layout.preferredWidth: 105
                                        text: modelData.time
                                        placeholderText: qsTr("拍位")
                                    }
                                    TextField {
                                        id: eventPitchField
                                        Layout.fillWidth: true
                                        text: modelData.pitches.join(", ")
                                        placeholderText: qsTr("鼓件音高")
                                    }
                                    FlatButton {
                                        text: qsTr("更新")
                                        onClicked: transcription.updateReviewEvent(
                                                       transcription.selectedReviewMeasure,
                                                       index,
                                                       eventTimeField.text,
                                                       eventPitchField.text)
                                    }
                                    FlatButton {
                                        text: qsTr("删除")
                                        onClicked: transcription.deleteReviewEvent(
                                                       transcription.selectedReviewMeasure,
                                                       index)
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTr("新增")
                                    color: ui.theme.fontSecondaryColor
                                }
                                TextField {
                                    id: newEventTimeField
                                    Layout.preferredWidth: 105
                                    placeholderText: qsTr("拍位")
                                }
                                TextField {
                                    id: newEventPitchField
                                    Layout.fillWidth: true
                                    placeholderText: qsTr("鼓件音高，如 36, 42")
                                }
                                FlatButton {
                                    text: qsTr("新增音符")
                                    onClicked: {
                                        if (transcription.addReviewEvent(
                                                    transcription.selectedReviewMeasure,
                                                    newEventTimeField.text,
                                                    newEventPitchField.text)) {
                                            newEventTimeField.text = ""
                                            newEventPitchField.text = ""
                                        }
                                    }
                                }
                            }

                            StyledTextLabel {
                                Layout.topMargin: 5
                                text: qsTr("休止符（声部：up / down）")
                                font: ui.theme.bodyBoldFont
                            }

                            ListView {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 154
                                clip: true
                                model: transcription.selectedReviewRests
                                spacing: 5

                                delegate: RowLayout {
                                    required property var modelData
                                    required property int index
                                    width: ListView.view.width
                                    spacing: 8

                                    StyledTextLabel {
                                        Layout.preferredWidth: 44
                                        text: "R" + (index + 1)
                                        color: ui.theme.fontSecondaryColor
                                    }
                                    TextField {
                                        id: restTimeField
                                        Layout.preferredWidth: 90
                                        text: modelData.time
                                    }
                                    TextField {
                                        id: restVoiceField
                                        Layout.preferredWidth: 70
                                        text: modelData.voice
                                    }
                                    TextField {
                                        id: restDurationField
                                        Layout.preferredWidth: 85
                                        text: modelData.duration
                                    }
                                    FlatButton {
                                        text: qsTr("更新")
                                        onClicked: transcription.updateReviewRest(
                                                       transcription.selectedReviewMeasure,
                                                       index,
                                                       restTimeField.text,
                                                       restVoiceField.text,
                                                       restDurationField.text)
                                    }
                                    FlatButton {
                                        text: qsTr("删除")
                                        onClicked: transcription.deleteReviewRest(
                                                       transcription.selectedReviewMeasure,
                                                       index)
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                StyledTextLabel {
                                    text: qsTr("新增休止符")
                                    color: ui.theme.fontSecondaryColor
                                }
                                TextField {
                                    id: newRestTimeField
                                    Layout.preferredWidth: 90
                                    placeholderText: qsTr("拍位")
                                }
                                TextField {
                                    id: newRestVoiceField
                                    Layout.preferredWidth: 70
                                    placeholderText: "up/down"
                                }
                                TextField {
                                    id: newRestDurationField
                                    Layout.preferredWidth: 85
                                    placeholderText: qsTr("时值")
                                }
                                FlatButton {
                                    text: qsTr("新增")
                                    onClicked: {
                                        if (transcription.addReviewRest(
                                                    transcription.selectedReviewMeasure,
                                                    newRestTimeField.text,
                                                    newRestVoiceField.text,
                                                    newRestDurationField.text)) {
                                            newRestTimeField.text = ""
                                            newRestVoiceField.text = ""
                                            newRestDurationField.text = ""
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: 16

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 256
                    radius: 16
                    color: root.imageMode ? "#F7FAFF" : ui.theme.backgroundPrimaryColor
                    border.color: root.imageMode ? "#8FB2EF" : ui.theme.strokeColor
                    border.width: root.imageMode ? 2 : 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 20
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Rectangle {
                                width: 46
                                height: 46
                                radius: 12
                                color: "#EAF2FF"
                                StyledTextLabel {
                                    anchors.centerIn: parent
                                    text: "▤"
                                    color: "#2F6EE5"
                                    font: ui.theme.titleBoldFont
                                }
                            }
                            StyledTextLabel {
                                Layout.fillWidth: true
                                text: qsTr("图片 / PDF 转鼓谱")
                                font: ui.theme.titleBoldFont
                                wrapMode: Text.WordWrap
                            }
                        }

                        Rectangle {
                            implicitWidth: imageReadyLabel.implicitWidth + 18
                            implicitHeight: 26
                            radius: 13
                            color: "#E8F8F0"
                            StyledTextLabel {
                                id: imageReadyLabel
                                anchors.centerIn: parent
                                text: qsTr("正式使用")
                                color: "#278A5B"
                                font: ui.theme.bodyBoldFont
                            }
                        }

                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTr("按原谱逐音符识别，生成可编辑的架子鼓鼓谱")
                            color: ui.theme.fontSecondaryColor
                            wrapMode: Text.WordWrap
                        }
                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTr("PNG / JPG / TIFF / PDF · 逐小节复核 · 严格校验")
                            color: ui.theme.fontSecondaryColor
                            font: ui.theme.bodyFont
                            wrapMode: Text.WordWrap
                        }

                        Item { Layout.fillHeight: true }

                        FlatButton {
                            Layout.fillWidth: true
                            text: root.imageMode ? qsTr("进入转谱工作区") : qsTr("切换到图片 / PDF")
                            accentButton: root.imageMode
                            enabled: !transcription.busy
                            onClicked: root.selectMode("image")
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 256
                    radius: 16
                    color: !root.imageMode ? "#F7FAFF" : ui.theme.backgroundPrimaryColor
                    border.color: !root.imageMode ? "#8FB2EF" : ui.theme.strokeColor
                    border.width: !root.imageMode ? 2 : 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 20
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Rectangle {
                                width: 46
                                height: 46
                                radius: 12
                                color: "#FFF1E7"
                                StyledTextLabel {
                                    anchors.centerIn: parent
                                    text: "♬"
                                    color: "#D8772C"
                                    font: ui.theme.titleBoldFont
                                }
                            }
                            StyledTextLabel {
                                Layout.fillWidth: true
                                text: qsTr("MIDI 转鼓谱")
                                font: ui.theme.titleBoldFont
                                wrapMode: Text.WordWrap
                            }
                        }

                        Rectangle {
                            implicitWidth: midiReadyLabel.implicitWidth + 18
                            implicitHeight: 26
                            radius: 13
                            color: "#FFF3DF"
                            StyledTextLabel {
                                id: midiReadyLabel
                                anchors.centerIn: parent
                                text: qsTr("开发调试中")
                                color: "#B5741F"
                                font: ui.theme.bodyBoldFont
                            }
                        }

                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTr("适配 YuE2、DAW 与电子鼓导出的 MIDI 文件")
                            color: ui.theme.fontSecondaryColor
                            wrapMode: Text.WordWrap
                        }
                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTr("读取鼓轨 · 节奏校正 · 标准化输出 DB Score 鼓谱")
                            color: ui.theme.fontSecondaryColor
                            font: ui.theme.bodyFont
                            wrapMode: Text.WordWrap
                        }

                        Item { Layout.fillHeight: true }

                        FlatButton {
                            Layout.fillWidth: true
                            text: root.imageMode ? qsTr("进入 MIDI 工作区") : qsTr("当前 MIDI 工作区")
                            accentButton: !root.imageMode
                            enabled: !transcription.busy
                            onClicked: root.selectMode("midi")
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 256
                    radius: 16
                    color: ui.theme.backgroundPrimaryColor
                    border.color: ui.theme.strokeColor

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 20
                        spacing: 10

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Rectangle {
                                width: 46
                                height: 46
                                radius: 12
                                color: "#F1F3F6"
                                StyledTextLabel {
                                    anchors.centerIn: parent
                                    text: "⌁"
                                    color: "#7D8A9B"
                                    font: ui.theme.titleBoldFont
                                }
                            }
                            StyledTextLabel {
                                Layout.fillWidth: true
                                text: qsTr("音频转鼓谱")
                                font: ui.theme.titleBoldFont
                                wrapMode: Text.WordWrap
                            }
                        }

                        Rectangle {
                            implicitWidth: audioPendingLabel.implicitWidth + 18
                            implicitHeight: 26
                            radius: 13
                            color: "#F1F3F6"
                            StyledTextLabel {
                                id: audioPendingLabel
                                anchors.centerIn: parent
                                text: qsTr("待开发")
                                color: "#8D98A8"
                                font: ui.theme.bodyBoldFont
                            }
                        }

                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTr("从完整歌曲直接识别架子鼓鼓谱")
                            color: ui.theme.fontSecondaryColor
                            wrapMode: Text.WordWrap
                        }
                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTr("预留音频输入、鼓轨分析与 .db 输出接口")
                            color: ui.theme.fontSecondaryColor
                            font: ui.theme.bodyFont
                            wrapMode: Text.WordWrap
                        }

                        Item { Layout.fillHeight: true }

                        FlatButton {
                            Layout.fillWidth: true
                            text: qsTr("待开发")
                            enabled: false
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 46
                radius: 10
                color: ui.theme.backgroundSecondaryColor
                border.color: ui.theme.strokeColor

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 7
                    spacing: 10

                    StyledTextLabel {
                        Layout.leftMargin: 8
                        text: root.imageMode
                              ? qsTr("当前工作区：图片 / PDF 转鼓谱")
                              : qsTr("当前工作区：MIDI 转鼓谱")
                        font: ui.theme.bodyBoldFont
                    }
                    Item { Layout.fillWidth: true }
                    FlatButton {
                        Layout.fillHeight: true
                        Layout.preferredWidth: 120
                        text: qsTr("继续复核")
                        enabled: !transcription.busy
                        onClicked: reviewProjectDialog.open()
                    }
                    StyledTextLabel {
                        text: qsTr("严格模式")
                        color: "#27845B"
                        font: ui.theme.bodyBoldFont
                        Layout.rightMargin: 10
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignTop
                spacing: 18

                Rectangle {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 520
                    Layout.preferredHeight: 410
                    radius: 14
                    color: ui.theme.backgroundPrimaryColor
                    border.color: ui.theme.strokeColor

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 24
                        spacing: 16

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 14

                            Rectangle {
                                width: 48
                                height: 48
                                radius: 13
                                color: root.imageMode ? "#FFF1E7" : "#EAF0FF"
                                StyledTextLabel {
                                    anchors.centerIn: parent
                                    text: root.imageMode ? "▤" : "♬"
                                    color: root.imageMode ? "#D8772C" : "#2F6EE5"
                                    font: ui.theme.titleBoldFont
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3
                                StyledTextLabel {
                                    text: root.imageMode ? qsTr("图片 / PDF 转鼓谱") : qsTr("MIDI 转鼓谱")
                                    font: ui.theme.titleBoldFont
                                }
                                StyledTextLabel {
                                    Layout.fillWidth: true
                                    text: root.imageMode
                                          ? qsTr("纸质鼓谱扫描件、乐谱截图或 PDF")
                                          : qsTr("适合 YuE2、DAW 与电子鼓导出的 MIDI")
                                    color: ui.theme.fontSecondaryColor
                                    font: ui.theme.bodyFont
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: root.imageMode ? 118 : 88
                            radius: 10
                            color: ui.theme.backgroundSecondaryColor
                            border.color: ui.theme.strokeColor

                            ColumnLayout {
                                anchors.fill: parent
                                anchors.margins: 16
                                spacing: 8

                                StyledTextLabel {
                                    text: root.imageMode ? qsTr("已选择页面") : qsTr("输入文件")
                                    font: ui.theme.bodyBoldFont
                                }
                                StyledTextLabel {
                                    Layout.fillWidth: true
                                    text: {
                                        if (root.imageMode) {
                                            if (root.imagePaths.length === 0)
                                                return qsTr("尚未选择鼓谱图片或 PDF")
                                            var names = []
                                            for (var i = 0; i < Math.min(3, root.imagePaths.length); ++i)
                                                names.push(root.fileName(root.imagePaths[i]))
                                            return names.join("　·　")
                                                   + (root.imagePaths.length > 3
                                                      ? qsTr("　等 %1 个文件").arg(root.imagePaths.length)
                                                      : "")
                                        }
                                        return root.midiPath
                                               ? root.fileName(root.midiPath)
                                               : qsTr("尚未选择 MIDI 文件")
                                    }
                                    color: (root.imageMode ? root.imagePaths.length > 0 : root.midiPath)
                                           ? ui.theme.fontPrimaryColor
                                           : ui.theme.fontSecondaryColor
                                    elide: Text.ElideMiddle
                                    wrapMode: Text.WordWrap
                                }
                                Item { Layout.fillHeight: true }
                                FlatButton {
                                    Layout.alignment: Qt.AlignRight
                                    text: root.imageMode ? qsTr("选择图片 / PDF") : qsTr("选择 MIDI 文件")
                                    accentButton: true
                                    enabled: !transcription.busy
                                    onClicked: root.imageMode ? imageDialog.open() : midiDialog.open()
                                }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10
                            StyledTextLabel {
                                text: qsTr("输出")
                                color: ui.theme.fontSecondaryColor
                            }
                            TextField {
                                Layout.fillWidth: true
                                readOnly: true
                                text: root.outputPath
                                placeholderText: qsTr("选择输入文件后自动生成")
                            }
                            FlatButton {
                                text: qsTr("另存为")
                                enabled: !transcription.busy
                                onClicked: outputDialog.open()
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12

                            BusyIndicator {
                                running: transcription.busy
                                visible: running
                                implicitWidth: 24
                                implicitHeight: 24
                            }

                            StyledTextLabel {
                                Layout.fillWidth: true
                                text: transcription.statusText.length > 0
                                      ? transcription.statusText
                                      : qsTr("选择文件后开始。只有全部严格校验通过才会生成最终 .db。")
                                color: transcription.completed ? "#20895A"
                                       : (transcription.reviewRequired ? "#B96B2D"
                                         : (root.currentReport.valid === false ? "#C74444"
                                                                               : ui.theme.fontPrimaryColor))
                                wrapMode: Text.WordWrap
                            }

                            FlatButton {
                                visible: transcription.busy
                                text: qsTr("停止")
                                onClicked: transcription.cancel()
                            }

                            FlatButton {
                                text: qsTr("开始转换")
                                accentButton: true
                                enabled: !transcription.busy
                                         && root.outputPath.length > 0
                                         && (root.imageMode ? root.imagePaths.length > 0
                                                            : root.midiPath.length > 0)
                                onClicked: root.startConversion()
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 340
                    Layout.fillHeight: true
                    Layout.minimumHeight: 410
                    radius: 14
                    color: ui.theme.backgroundPrimaryColor
                    border.color: ui.theme.strokeColor

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 22
                        spacing: 14

                        StyledTextLabel {
                            text: qsTr("转换设置")
                            font: ui.theme.titleBoldFont
                        }

                        StyledTextLabel {
                            text: qsTr("输出格式")
                            color: ui.theme.fontSecondaryColor
                            font: ui.theme.bodyFont
                        }
                        TextField {
                            Layout.fillWidth: true
                            readOnly: true
                            text: qsTr("DB Score 鼓谱 · .db")
                        }

                        StyledTextLabel {
                            visible: !root.imageMode
                            text: qsTr("节奏网格")
                            color: ui.theme.fontSecondaryColor
                            font: ui.theme.bodyFont
                        }
                        ComboBox {
                            id: gridCombo
                            visible: !root.imageMode
                            Layout.fillWidth: true
                            enabled: !transcription.busy
                            textRole: "label"
                            valueRole: "value"
                            model: [
                                { label: qsTr("自动识别"), value: "auto" },
                                { label: "1/8", value: "8" },
                                { label: "1/8 三连音", value: "8t" },
                                { label: "1/16", value: "16" },
                                { label: "1/16 三连音", value: "16t" },
                                { label: "1/32", value: "32" }
                            ]
                        }

                        StyledTextLabel {
                            visible: !root.imageMode
                            text: qsTr("速度")
                            color: ui.theme.fontSecondaryColor
                            font: ui.theme.bodyFont
                        }
                        ComboBox {
                            id: bpmMode
                            visible: !root.imageMode
                            Layout.fillWidth: true
                            enabled: !transcription.busy
                            textRole: "label"
                            valueRole: "value"
                            model: [
                                { label: qsTr("自动识别"), value: "auto" },
                                { label: qsTr("使用文件原速度"), value: "source" },
                                { label: qsTr("手动指定"), value: "manual" }
                            ]
                        }
                        TextField {
                            id: bpmField
                            visible: !root.imageMode && bpmMode.currentValue === "manual"
                            Layout.fillWidth: true
                            placeholderText: qsTr("BPM")
                            validator: DoubleValidator {
                                bottom: 30
                                top: 300
                                decimals: 2
                            }
                        }

                        StyledTextLabel {
                            visible: !root.imageMode
                            text: qsTr("起始对齐")
                            color: ui.theme.fontSecondaryColor
                            font: ui.theme.bodyFont
                        }
                        ComboBox {
                            id: shiftCombo
                            visible: !root.imageMode
                            Layout.fillWidth: true
                            enabled: !transcription.busy
                            textRole: "label"
                            valueRole: "value"
                            model: [
                                { label: qsTr("自动对齐首镲"), value: "auto" },
                                { label: qsTr("不移动"), value: "none" },
                                { label: qsTr("向前 1/16"), value: "left-1/16" },
                                { label: qsTr("向前 1/8"), value: "left-1/8" },
                                { label: qsTr("向前 1/4"), value: "left-1/4" },
                                { label: qsTr("向后 1/16"), value: "right-1/16" },
                                { label: qsTr("向后 1/8"), value: "right-1/8" }
                            ]
                        }

                        RowLayout {
                            visible: !root.imageMode
                            Layout.fillWidth: true
                            StyledTextLabel {
                                Layout.fillWidth: true
                                text: qsTr("前置休止小节")
                                color: ui.theme.fontSecondaryColor
                            }
                            SpinBox {
                                id: leadingMeasureSpin
                                from: 0
                                to: 8
                                value: root.leadingMeasures
                                enabled: !transcription.busy
                                onValueModified: root.leadingMeasures = value
                            }
                        }

                        StyledTextLabel {
                            visible: root.imageMode
                            text: qsTr("曲名")
                            color: ui.theme.fontSecondaryColor
                            font: ui.theme.bodyFont
                        }
                        TextField {
                            visible: root.imageMode
                            Layout.fillWidth: true
                            text: root.imageTitle
                            placeholderText: qsTr("输入曲名")
                            enabled: !transcription.busy
                            onTextEdited: root.imageTitle = text
                        }

                        RowLayout {
                            visible: root.imageMode
                            Layout.fillWidth: true
                            StyledTextLabel {
                                Layout.fillWidth: true
                                text: qsTr("BPM")
                                color: ui.theme.fontSecondaryColor
                            }
                            SpinBox {
                                from: 20
                                to: 400
                                value: root.imageTempo
                                enabled: !transcription.busy
                                onValueModified: root.imageTempo = value
                            }
                        }

                        Item { Layout.fillHeight: true }

                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: validationColumn.implicitHeight + 26
                            radius: 9
                            color: root.strictValid ? "#F1FAF5" : ui.theme.backgroundSecondaryColor
                            border.color: root.strictValid ? "#CFE8D9" : ui.theme.strokeColor

                            ColumnLayout {
                                id: validationColumn
                                anchors.fill: parent
                                anchors.margins: 13
                                spacing: 5
                                StyledTextLabel {
                                    text: qsTr("严格校验")
                                    color: root.strictValid ? "#287D58" : ui.theme.fontSecondaryColor
                                    font: ui.theme.bodyBoldFont
                                }
                                StyledTextLabel {
                                    text: root.strictValid ? qsTr("全部通过") : qsTr("等待转换")
                                    color: root.strictValid ? "#269366" : ui.theme.fontSecondaryColor
                                    font: ui.theme.bodyFont
                                }
                                StyledTextLabel {
                                    visible: root.currentReport.exactTimelineMatch !== undefined
                                    text: qsTr("逐事件时间轴：%1")
                                          .arg(root.currentReport.exactTimelineMatch ? qsTr("完全一致") : qsTr("未通过"))
                                    color: root.currentReport.exactTimelineMatch ? "#269366" : "#C74444"
                                    font: ui.theme.bodyFont
                                }
                            }
                        }

                        RowLayout {
                            visible: transcription.completed
                            Layout.fillWidth: true
                            spacing: 8
                            FlatButton {
                                Layout.fillWidth: true
                                text: qsTr("编辑乐谱")
                                accentButton: true
                                enabled: transcription.completed
                                         && /\.db$/i.test(transcription.outputPath)
                                onClicked: transcription.openOutputInScore()
                            }
                            FlatButton {
                                Layout.fillWidth: true
                                text: qsTr("显示位置")
                                onClicked: transcription.revealOutput()
                            }
                        }
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                visible: root.diagnosticsVisible
                implicitHeight: diagnosticsColumn.implicitHeight + 28
                radius: 12
                color: ui.theme.backgroundPrimaryColor
                border.color: ui.theme.strokeColor

                ColumnLayout {
                    id: diagnosticsColumn
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8
                    StyledTextLabel {
                        text: qsTr("转换环境")
                        font: ui.theme.bodyBoldFont
                    }
                    TextArea {
                        Layout.fillWidth: true
                        readOnly: true
                        wrapMode: TextEdit.Wrap
                        background: null
                        text: transcription.environmentDiagnostics()
                        font: ui.theme.bodyFont
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                visible: transcription.logText.length > 0
                implicitHeight: 140
                radius: 12
                color: ui.theme.backgroundPrimaryColor
                border.color: ui.theme.strokeColor
                clip: true

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 12
                    TextArea {
                        readOnly: true
                        wrapMode: TextEdit.Wrap
                        text: transcription.logText
                        background: null
                        font: ui.theme.bodyFont
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 128
                radius: 14
                color: ui.theme.backgroundPrimaryColor
                border.color: ui.theme.strokeColor

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 22
                    spacing: 26

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 7
                        StyledTextLabel {
                            text: qsTr("DB Score 排版标准")
                            font: ui.theme.bodyBoldFont
                        }
                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTr("上声部：军鼓、桶鼓与镲片，符干向上；下声部：底鼓与踩镲踏板，符干向下。")
                            color: ui.theme.fontSecondaryColor
                            wrapMode: Text.WordWrap
                            font: ui.theme.bodyFont
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        color: ui.theme.strokeColor
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 7
                        StyledTextLabel {
                            text: qsTr("严格输出")
                            font: ui.theme.bodyBoldFont
                        }
                        StyledTextLabel {
                            Layout.fillWidth: true
                            text: qsTr("只要存在未映射鼓件、节奏未确认、小节时值错误或时间轴不一致，就不会生成最终文件。")
                            color: ui.theme.fontSecondaryColor
                            wrapMode: Text.WordWrap
                            font: ui.theme.bodyFont
                        }
                    }
                }
            }
        }
    }
        }
    }
}
