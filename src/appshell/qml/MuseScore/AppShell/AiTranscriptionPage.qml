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
    property string imageTempoText: "120"
    property int leadingMeasures: 0
    property bool diagnosticsVisible: false
    property bool dropHovered: false
    property int reviewPageIndex: 0
    property real reviewZoom: 1.0

    readonly property bool imageMode: mode === "image"
    readonly property var currentReport: transcription.report
    readonly property bool strictValid: currentReport.valid === true

    readonly property color pageBackgroundColor: ui.theme.backgroundPrimaryColor
    readonly property color cardBackgroundColor: ui.theme.popupBackgroundColor
    readonly property color insetBackgroundColor: ui.theme.backgroundSecondaryColor
    readonly property color separatorColor: ui.theme.strokeColor
    readonly property color accentSoftColor: Utils.colorWithAlpha(ui.theme.accentColor,
                                                                  ui.theme.isDark ? 0.24 : 0.14)
    readonly property color successSoftColor: ui.theme.isDark ? "#1B3A2A" : "#E8F8F0"
    readonly property color warningSoftColor: Utils.colorWithAlpha(ui.theme.linkColor,
                                                                   ui.theme.isDark ? 0.2 : 0.1)
    readonly property color successTextColor: ui.theme.isDark ? "#8BE6AE" : "#20895A"
    readonly property color warningTextColor: ui.theme.isDark ? "#FFB26B" : "#B96B2D"
    readonly property color errorTextColor: ui.theme.isDark ? "#FF8B8B" : "#C74444"

    readonly property int currentStep:
        transcription.completed ? 5
        : transcription.busy ? 3
        : transcription.reviewRequired ? 3
        : (imagePaths.length > 0 || midiPath.length > 0) ? 2 : 1

    function pathText(value) {
        if (!value)
            return ""
        var text = value.toString()
        return transcription.normalizeInputPath(text)
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

    function isSupportedInput(path, imageMode) {
        if (!path)
            return false
        return imageMode
                ? /\.(png|jpe?g|tiff?|bmp|webp|pdf)$/i.test(path)
                : /\.(midi?)$/i.test(path)
    }

    function acceptDroppedUrls(urls) {
        if (transcription.busy || !urls)
            return
        var paths = []
        for (var i = 0; i < urls.length; ++i) {
            var path = pathText(urls[i])
            if (isSupportedInput(path, imageMode))
                paths.push(path)
        }
        if (paths.length === 0) {
            transcription.showError(imageMode
                                    ? qsTr("请拖入图片或 PDF 鼓谱")
                                    : qsTr("请拖入 MIDI 文件"))
            return
        }
        transcription.reset()
        if (imageMode) {
            imagePaths = paths
            imageTitle = suggestedTitle(paths[0])
        } else {
            midiPath = paths[0]
            imageTitle = suggestedTitle(paths[0])
        }
        outputPath = suggestedOutput(paths[0])
        transcription.showError("")
    }

    function selectReviewPage(index) {
        if (index < 0 || index >= transcription.reviewPages.length)
            return
        reviewPageIndex = index
        var firstMeasure = transcription.reviewPages[index].firstMeasure
        if (firstMeasure > 0)
            transcription.selectReviewMeasure(firstMeasure)
    }

    function showReviewMeasure(measureNumber) {
        transcription.selectReviewMeasure(measureNumber)
        for (var i = 0; i < transcription.reviewPages.length; ++i) {
            var page = transcription.reviewPages[i]
            if (measureNumber >= page.firstMeasure
                    && measureNumber <= page.lastMeasure) {
                reviewPageIndex = i
                break
            }
        }
    }

    function fileUrl(path) {
        if (!path)
            return ""
        return transcription.localFileUrl(path)
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
                parseFloat(imageTempoText) || 120
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

    Connections {
        target: transcription

        function onReviewStateChanged() {
            if (root.reviewPageIndex >= transcription.reviewPages.length)
                root.reviewPageIndex = 0
        }
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
            var urls = (typeof files !== "undefined") ? files : []
            var paths = []
            for (var i = 0; i < urls.length; ++i)
                paths.push(root.pathText(urls[i]))
            root.imagePaths = paths
            transcription.reset()
            if (paths.length > 0) {
                root.outputPath = root.suggestedOutput(paths[0])
                if (!root.imageTitle)
                    root.imageTitle = root.suggestedTitle(paths[0])
            } else {
                transcription.showError(qsTr("未读取到所选图片，请重试"))
            }
        }
    }

    FileDialog {
        id: outputDialog
        title: qsTr("保存 DB绘谱鼓谱")
        fileMode: FileDialog.SaveFile
        nameFilters: [qsTr("DB绘谱鼓谱 (*.db)")]
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
                color: root.pageBackgroundColor
            }

            Flickable {
                id: scroller
                anchors.fill: parent
                clip: true
                contentWidth: width
                contentHeight: contentColumn.height + 48
                boundsBehavior: Flickable.StopAtBounds

                ColumnLayout {
                    id: contentColumn
                    x: 48
                    y: 32
                    width: Math.max(1, scroller.width - 96)
                    spacing: 20

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 14

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6

                            RowLayout {
                                spacing: 12
                                StyledTextLabel {
                                    text: qsTr("AI 转谱")
                                    font: ui.theme.titleBoldFont
                                }
                                Rectangle {
                                    implicitWidth: poweredLabel.implicitWidth + 18
                                    implicitHeight: 26
                                    radius: 13
                                    color: root.accentSoftColor
                                    StyledTextLabel {
                                        id: poweredLabel
                                        anchors.centerIn: parent
                                        text: "✦ AI POWERED · P1.0.0"
                                        color: "#EA580C"
                                        font: ui.theme.bodyBoldFont
                                    }
                                }
                            }

                            StyledTextLabel {
                                Layout.fillWidth: true
                                text: qsTr("鼓 MIDI 标准化，适配 DB绘谱鼓谱")
                                color: ui.theme.fontSecondaryColor
                                font: ui.theme.bodyFont
                            }
                        }

                        FlatButton {
                            text: qsTr("打开复核资料")
                            visible: transcription.reviewRequired
                            onClicked: transcription.revealReviewProject()
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
                        radius: 16
                        color: root.cardBackgroundColor
                        border.color: root.separatorColor

                        ColumnLayout {
                            id: reviewLayout
                            anchors.fill: parent
                            anchors.margins: 20
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
                                           ? root.successTextColor : root.warningTextColor
                                    font: ui.theme.bodyBoldFont
                                }
                                FlatButton {
                                    text: qsTr("全部标记已确认")
                                    enabled: !transcription.busy
                                             && transcription.reviewMeasureCount > 0
                                             && transcription.reviewedMeasureCount < transcription.reviewMeasureCount
                                    onClicked: transcription.markAllMeasuresReviewed()
                                }
                                FlatButton {
                                    text: qsTr("生成正式鼓谱")
                                    accentButton: true
                                    enabled: !transcription.busy
                                             && transcription.reviewedMeasureCount === transcription.reviewMeasureCount
                                    onClicked: transcription.finalizeImageReview()
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 12

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 300
                                    radius: 9
                                    color: root.insetBackgroundColor
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
                                        Flickable {
                                            id: originalFlick
                                            Layout.fillWidth: true
                                            Layout.fillHeight: true
                                            clip: true
                                            contentWidth: Math.max(width, width * root.reviewZoom)
                                            contentHeight: Math.max(height, height * root.reviewZoom)
                                            Image {
                                                width: originalFlick.width * root.reviewZoom
                                                height: originalFlick.height * root.reviewZoom
                                                fillMode: Image.PreserveAspectFit
                                                source: transcription.reviewPages.length > root.reviewPageIndex
                                                        ? root.fileUrl(transcription.reviewPages[root.reviewPageIndex].original)
                                                        : ""
                                            }
                                        }
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 300
                                    radius: 9
                                    color: root.insetBackgroundColor
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
                                        Flickable {
                                            id: generatedFlick
                                            Layout.fillWidth: true
                                            Layout.fillHeight: true
                                            clip: true
                                            contentWidth: Math.max(width, width * root.reviewZoom)
                                            contentHeight: Math.max(height, height * root.reviewZoom)
                                            Image {
                                                width: generatedFlick.width * root.reviewZoom
                                                height: generatedFlick.height * root.reviewZoom
                                                fillMode: Image.PreserveAspectFit
                                                source: transcription.reviewPages.length > root.reviewPageIndex
                                                        ? root.fileUrl(transcription.reviewPages[root.reviewPageIndex].generated)
                                                        : ""
                                            }
                                        }
                                    }
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                FlatButton {
                                    text: qsTr("上一页")
                                    enabled: root.reviewPageIndex > 0
                                    onClicked: root.selectReviewPage(root.reviewPageIndex - 1)
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
                                    onClicked: root.selectReviewPage(root.reviewPageIndex + 1)
                                }
                                FlatButton {
                                    text: "－"
                                    enabled: root.reviewZoom > 1.0
                                    onClicked: root.reviewZoom = Math.max(1.0, root.reviewZoom - 0.25)
                                }
                                StyledTextLabel {
                                    text: Math.round(root.reviewZoom * 100) + "%"
                                    color: ui.theme.fontSecondaryColor
                                }
                                FlatButton {
                                    text: "＋"
                                    enabled: root.reviewZoom < 4.0
                                    onClicked: root.reviewZoom = Math.min(4.0, root.reviewZoom + 0.25)
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 240
                                radius: 9
                                color: root.insetBackgroundColor
                                border.color: root.separatorColor
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
                                        height: 40
                                        radius: 6
                                        color: modelData.reviewed ? root.successSoftColor
                                                                 : ((modelData.unresolvedCount > 0
                                                                     || modelData.reviewReasonCount > 0)
                                                                    ? root.warningSoftColor
                                                                    : root.cardBackgroundColor)

                                        MouseArea {
                                            anchors.fill: parent
                                            onClicked: root.showReviewMeasure(modelData.number)
                                        }

                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 10
                                            anchors.rightMargin: 10
                                            CheckBox {
                                                checked: modelData.reviewed
                                                enabled: !transcription.busy
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
                                                       ? root.warningTextColor : ui.theme.fontSecondaryColor
                                                elide: Text.ElideRight
                                            }
                                        }
                                    }
                                }
                            }

                            // 事件修正（选中某小节后在这里修正休止符/音符）
                            Rectangle {
                                Layout.fillWidth: true
                                visible: transcription.selectedReviewMeasure > 0
                                enabled: !transcription.busy
                                implicitHeight: eventEditorColumn.implicitHeight + 24
                                radius: 9
                                color: root.insetBackgroundColor
                                border.color: root.separatorColor

                                ColumnLayout {
                                    id: eventEditorColumn
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 8

                                    StyledTextLabel {
                                        text: qsTr("事件修正 · 第 %1 小节").arg(transcription.selectedReviewMeasure)
                                        font: ui.theme.bodyBoldFont
                                    }

                                    StyledTextLabel {
                                        Layout.fillWidth: true
                                        text: qsTr("休止符（声部：up / down；时值：whole / half / quarter / eighth / 16th）")
                                        color: ui.theme.fontSecondaryColor
                                        wrapMode: Text.WordWrap
                                    }

                                    ListView {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 150
                                        clip: true
                                        model: transcription.selectedReviewRests
                                        spacing: 5

                                        delegate: RowLayout {
                                            required property var modelData
                                            required property int index
                                            width: ListView.view.width
                                            spacing: 8

                                            StyledTextLabel {
                                                Layout.preferredWidth: 40
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
                                                Layout.preferredWidth: 90
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
                                            Layout.preferredWidth: 90
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

                                    StyledTextLabel {
                                        Layout.topMargin: 4
                                        text: qsTr("音符（拍位 + 鼓件 GM 音高，用逗号分隔）")
                                        color: ui.theme.fontSecondaryColor
                                        wrapMode: Text.WordWrap
                                    }

                                    ListView {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 150
                                        clip: true
                                        model: transcription.selectedReviewEvents
                                        spacing: 5

                                        delegate: RowLayout {
                                            required property var modelData
                                            required property int index
                                            width: ListView.view.width
                                            spacing: 8

                                            StyledTextLabel {
                                                Layout.preferredWidth: 40
                                                text: "#" + (index + 1)
                                                color: ui.theme.fontSecondaryColor
                                            }
                                            TextField {
                                                id: eventTimeField
                                                Layout.preferredWidth: 90
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
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.alignment: Qt.AlignTop
                        spacing: 24

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: importColumn.implicitHeight + 48
                            radius: 16
                            color: root.cardBackgroundColor
                            border.color: root.separatorColor

                            ColumnLayout {
                                id: importColumn
                                anchors.fill: parent
                                anchors.margins: 24
                                spacing: 16

                                StyledTextLabel {
                                    text: qsTr("导入鼓谱")
                                    font: ui.theme.titleBoldFont
                                }
                                StyledTextLabel {
                                    Layout.fillWidth: true
                                    text: qsTr("选择源文件，AI 将按 DB绘谱 的两声部鼓谱规范完成识别与校验。")
                                    color: ui.theme.fontSecondaryColor
                                    wrapMode: Text.WordWrap
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    FlatButton {
                                        text: qsTr("图片 / PDF 鼓谱")
                                        accentButton: root.imageMode
                                        onClicked: root.selectMode("image")
                                    }
                                    FlatButton {
                                        text: qsTr("MIDI 文件")
                                        accentButton: !root.imageMode
                                        onClicked: root.selectMode("midi")
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 150
                                    radius: 12
                                    color: root.dropHovered ? root.accentSoftColor : root.insetBackgroundColor
                                    border.color: root.dropHovered ? ui.theme.accentColor : root.separatorColor
                                    border.width: root.dropHovered ? 2 : 1

                                    DropArea {
                                        anchors.fill: parent
                                        z: 2

                                        onEntered: root.dropHovered = true
                                        onExited: root.dropHovered = false
                                        onDropped: {
                                            root.dropHovered = false
                                            if (drop.hasUrls)
                                                root.acceptDroppedUrls(drop.urls)
                                        }
                                    }

                                    ColumnLayout {
                                        anchors.centerIn: parent
                                        spacing: 8
                                        StyledTextLabel {
                                            Layout.alignment: Qt.AlignHCenter
                                            text: root.imageMode
                                                  ? qsTr("拖入鼓谱图片或 PDF")
                                                  : qsTr("拖入 MIDI 文件")
                                            font: ui.theme.bodyBoldFont
                                        }
                                        StyledTextLabel {
                                            Layout.alignment: Qt.AlignHCenter
                                            text: root.imageMode
                                                  ? qsTr("支持 PNG、JPG、TIFF、PDF，可一次导入多页")
                                                  : qsTr("适配 YuE2、DAW 与电子鼓导出的 MIDI")
                                            color: ui.theme.fontSecondaryColor
                                            font: ui.theme.bodyFont
                                        }
                                        FlatButton {
                                            Layout.alignment: Qt.AlignHCenter
                                            Layout.preferredWidth: 180
                                            Layout.preferredHeight: 38
                                            text: qsTr("上传文件")
                                            accentButton: true
                                            enabled: !transcription.busy
                                            onClicked: root.imageMode ? imageDialog.open() : midiDialog.open()
                                        }
                                    }
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
                                                      ? qsTr("　等 %1 个文件").arg(root.imagePaths.length) : "")
                                        }
                                        return root.midiPath ? root.fileName(root.midiPath) : qsTr("尚未选择 MIDI 文件")
                                    }
                                    color: ui.theme.fontPrimaryColor
                                    elide: Text.ElideMiddle
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    StyledTextLabel {
                                        Layout.preferredWidth: 68
                                        text: qsTr("曲名")
                                        color: ui.theme.fontSecondaryColor
                                    }
                                    TextField {
                                        Layout.fillWidth: true
                                        text: root.imageTitle
                                        placeholderText: qsTr("曲名")
                                        onTextEdited: root.imageTitle = text
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    StyledTextLabel {
                                        Layout.preferredWidth: 68
                                        text: qsTr("速度")
                                        color: ui.theme.fontSecondaryColor
                                    }
                                    TextField {
                                        Layout.fillWidth: true
                                        text: root.imageTempoText
                                        enabled: !transcription.busy
                                        validator: DoubleValidator {
                                            bottom: 20
                                            top: 400
                                            decimals: 3
                                        }
                                        onTextEdited: root.imageTempoText = text
                                    }
                                    StyledTextLabel {
                                        text: qsTr("BPM")
                                        color: ui.theme.fontSecondaryColor
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: 8
                                    StyledTextLabel {
                                        Layout.preferredWidth: 68
                                        text: qsTr("输出位置")
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

                                ColumnLayout {
                                    visible: !root.imageMode
                                    Layout.fillWidth: true
                                    spacing: 8

                                    RowLayout {
                                        Layout.fillWidth: true
                                        StyledTextLabel {
                                            Layout.preferredWidth: 68
                                            text: qsTr("节奏网格")
                                            color: ui.theme.fontSecondaryColor
                                        }
                                        ComboBox {
                                            id: gridCombo
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
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        StyledTextLabel {
                                            Layout.preferredWidth: 68
                                            text: qsTr("速度来源")
                                            color: ui.theme.fontSecondaryColor
                                        }
                                        ComboBox {
                                            id: bpmMode
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
                                    }

                                    TextField {
                                        id: bpmField
                                        visible: bpmMode.currentValue === "manual"
                                        Layout.fillWidth: true
                                        placeholderText: qsTr("BPM")
                                        validator: DoubleValidator {
                                            bottom: 30
                                            top: 300
                                            decimals: 2
                                        }
                                    }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        StyledTextLabel {
                                            Layout.preferredWidth: 68
                                            text: qsTr("起始对齐")
                                            color: ui.theme.fontSecondaryColor
                                        }
                                        ComboBox {
                                            id: shiftCombo
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
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: flowColumn.implicitHeight + 48
                            radius: 16
                            color: root.cardBackgroundColor
                            border.color: root.separatorColor

                            ColumnLayout {
                                id: flowColumn
                                anchors.fill: parent
                                anchors.margins: 24
                                spacing: 14

                                StyledTextLabel {
                                    text: qsTr("转谱流程")
                                    font: ui.theme.titleBoldFont
                                }
                                StyledTextLabel {
                                    Layout.fillWidth: true
                                    text: qsTr("从原谱到可编辑.db，全程本机完成")
                                    color: ui.theme.fontSecondaryColor
                                }

                                Repeater {
                                    model: [
                                        { n: "01", t: qsTr("上传原谱"), d: qsTr("图片、PDF 或 MIDI") },
                                        { n: "02", t: qsTr("AI 识别"), d: qsTr("音符、鼓件、休止符、连线") },
                                        { n: "03", t: qsTr("结构与节奏校验"), d: qsTr("自动检查音高、时值和声部") },
                                        { n: "04", t: qsTr("生成 DB 鼓谱"), d: qsTr("自动保存为可编辑 .db 文件") },
                                        { n: "05", t: qsTr("进入乐谱编辑"), d: qsTr("识别结果可直接修改") }
                                    ]

                                    RowLayout {
                                        required property var modelData
                                        required property int index
                                        Layout.fillWidth: true
                                        spacing: 12

                                        Rectangle {
                                            width: 30
                                            height: 30
                                            radius: 15
                                            color: (index + 1) === root.currentStep ? "#EA580C"
                                                   : (index + 1) < root.currentStep
                                                     ? root.successSoftColor : root.insetBackgroundColor
                                            StyledTextLabel {
                                                anchors.centerIn: parent
                                                text: (index + 1) < root.currentStep ? "✓" : modelData.n
                                                color: (index + 1) === root.currentStep ? "#FFFFFF"
                                                       : (index + 1) < root.currentStep
                                                         ? root.successTextColor : ui.theme.fontSecondaryColor
                                                font: ui.theme.bodyBoldFont
                                            }
                                        }

                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            StyledTextLabel {
                                                text: modelData.t
                                                font: ui.theme.bodyBoldFont
                                            }
                                            StyledTextLabel {
                                                Layout.fillWidth: true
                                                text: modelData.d
                                                color: ui.theme.fontSecondaryColor
                                                font: ui.theme.bodyFont
                                                wrapMode: Text.WordWrap
                                            }
                                        }
                                    }
                                }

                                StyledTextLabel {
                                    Layout.fillWidth: true
                                    text: transcription.statusText.length > 0
                                          ? transcription.statusText
                                          : qsTr("上传文件后开始。识别完成会直接生成可编辑的 .db 鼓谱。")
                                    color: transcription.completed ? root.successTextColor
                                           : (transcription.reviewRequired ? root.warningTextColor
                                              : (root.currentReport.valid === false
                                                 ? root.errorTextColor : ui.theme.fontPrimaryColor))
                                    wrapMode: Text.WordWrap
                                }

                                FlatButton {
                                    Layout.fillWidth: true
                                    visible: !transcription.reviewRequired || transcription.busy
                                    text: transcription.busy ? qsTr("停止")
                                          : (transcription.completed ? qsTr("重新转谱") : qsTr("开始转谱"))
                                    accentButton: !transcription.busy && !transcription.completed
                                    enabled: !transcription.busy
                                             && root.outputPath.length > 0
                                             && (root.imageMode ? root.imagePaths.length > 0 : root.midiPath.length > 0)
                                    onClicked: transcription.busy ? transcription.cancel() : root.startConversion()
                                }

                                FlatButton {
                                    Layout.fillWidth: true
                                    visible: transcription.completed
                                    text: qsTr("编辑乐谱")
                                    accentButton: true
                                    onClicked: transcription.openOutputInScore()
                                }

                                StyledTextLabel {
                                    Layout.fillWidth: true
                                    text: qsTr("预计 15-30 秒 • 本机处理")
                                    color: ui.theme.fontSecondaryColor
                                    font: ui.theme.bodyFont
                                    horizontalAlignment: Text.AlignHCenter
                                }
                            }
                        }
                    }

                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTr("建议使用完整鼓谱页；页面越清晰，鼓件、休止符和连音线识别越稳定。")
                        color: ui.theme.fontSecondaryColor
                        wrapMode: Text.WordWrap
                    }
                    StyledTextLabel {
                        Layout.fillWidth: true
                        text: qsTr("系统会自动完成音高、时值、声部和连线结构校验；识别完成后直接生成可编辑鼓谱。")
                        color: ui.theme.fontSecondaryColor
                        wrapMode: Text.WordWrap
                    }
                }
            }
        }
    }
}
