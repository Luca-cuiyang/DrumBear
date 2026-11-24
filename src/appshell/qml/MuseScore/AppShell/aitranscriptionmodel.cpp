/*
 * SPDX-License-Identifier: GPL-3.0-only
 */

#include "aitranscriptionmodel.h"

#include <algorithm>

#include <QCoreApplication>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcessEnvironment>
#include <QSaveFile>
#include <QSet>
#include <QStandardPaths>
#include <QSysInfo>
#include <QTimer>
#include <QUrl>

#include "actions/actiontypes.h"

using namespace mu::appshell;
using namespace muse::actions;

static QString localPathFromInput(const QString& value)
{
    const QUrl url(value);
    QString path = url.isLocalFile() ? url.toLocalFile() : value;
    if (path.isEmpty()) {
        return {};
    }

    //! File dialogs commonly return file:///C:/... on Windows. QUrl may expose
    //! that local path as /C:/..., which is not an absolute Windows drive path.
    if (path.size() >= 3
        && path.at(0) == '/'
        && path.at(1).isLetter()
        && path.at(2) == ':') {
        path.remove(0, 1);
    }

    return QDir::cleanPath(path);
}

static double fractionValue(const QString& value, bool* ok = nullptr)
{
    const QStringList parts = value.trimmed().split('/');
    bool numeratorOk = false;
    const double numerator = parts.value(0).trimmed().toDouble(&numeratorOk);
    double denominator = 1.0;
    bool denominatorOk = true;
    if (parts.size() > 1) {
        denominator = parts.value(1).trimmed().toDouble(&denominatorOk);
    }
    const bool valid = numeratorOk && denominatorOk && denominator > 0
                       && parts.size() <= 2;
    if (ok) {
        *ok = valid;
    }
    return valid ? numerator / denominator : 0.0;
}

static int jobTimeoutMilliseconds()
{
    bool ok = false;
    const int configured = qEnvironmentVariableIntValue(
        "DBSCORE_AI_JOB_TIMEOUT_MS",
        &ok);
    if (ok && configured >= 30000 && configured <= 4 * 60 * 60 * 1000) {
        return configured;
    }
    return 30 * 60 * 1000;
}

static QString localizedJobError(const QString& value)
{
    const QString detail = value.trimmed();
    if (detail.contains("鼓谱文件不存在")) {
        return QObject::tr("找不到所选原图片或 PDF。请重新选择文件后再试");
    }
    if (detail.contains("No module named 'cv2'")) {
        return QObject::tr("图片转谱运行库缺少 OpenCV，请安装完整程序包后重试");
    }
    if (detail.contains("No module named 'numpy'")) {
        return QObject::tr("图片转谱运行库缺少 NumPy，请安装完整程序包后重试");
    }
    if (detail.contains("No module named 'PIL'")) {
        return QObject::tr("图片转谱运行库缺少 Pillow，请安装完整程序包后重试");
    }
    if (detail.contains("Command timed out")) {
        return QObject::tr("转谱命令超时，任务已停止；请查看日志后重试");
    }
    if (detail.contains("DB绘谱 timed out")) {
        return QObject::tr("DB绘谱 生成文件超时，请关闭其他乐谱窗口后重试");
    }
    if (detail.contains("DB绘谱 failed")) {
        return QObject::tr("DB绘谱 生成文件失败，请查看日志后重试");
    }
    if ((detail.contains("Command failed") && detail.contains("Audiveris"))
        || (detail.contains("FileNotFoundError") && detail.contains(".mxl"))
        || detail.contains("too low interline value")
        || detail.contains("Sheet ignored")
        || detail.contains("Error in reaching step PAGE")) {
        return QObject::tr(
            "Audiveris 无法识别这张图片：分辨率过低或页面中没有可识别的五线谱。"
            "请使用 300 DPI 以上的完整鼓谱图片，并确保谱线清晰、页面未裁切。"
            "如果原图清晰，请打开转谱日志查看具体原因");
    }
    return detail.left(400);
}

AiTranscriptionModel::AiTranscriptionModel(QObject* parent)
    : QObject(parent), muse::Contextable(muse::iocCtxForQmlObject(this))
{
    m_jobTimeoutTimer.setSingleShot(true);
    m_process.setProcessChannelMode(QProcess::MergedChannels);
    m_process.setProcessEnvironment(QProcessEnvironment::systemEnvironment());

    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this]() {
        readProcessOutput();
    });
    connect(&m_jobTimeoutTimer, &QTimer::timeout, this, [this]() {
        if (!busy() || m_process.state() == QProcess::NotRunning) {
            return;
        }
        const int generation = m_processGeneration;
        m_timeoutRequested = true;
        setStatusText(tr("转谱超过 %1 分钟仍未完成，正在停止任务…")
                          .arg(jobTimeoutMilliseconds() / 60000));
        m_process.terminate();
        QTimer::singleShot(3000, this, [this, generation]() {
            if (generation == m_processGeneration
                && m_process.state() != QProcess::NotRunning) {
                m_process.kill();
            }
        });
    });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) {
            m_jobTimeoutTimer.stop();
            setBusy(false);
            setCompleted(false);
            setStatusText(tr("无法启动 AI 转谱引擎：%1").arg(m_process.errorString()));
            appendLog(m_process.errorString());
        }
    });
    connect(
        &m_process,
        qOverload<int, QProcess::ExitStatus>(&QProcess::finished),
        this,
        [this](int exitCode, QProcess::ExitStatus exitStatus) {
            finishJob(exitCode, exitStatus);
        });
}

AiTranscriptionModel::~AiTranscriptionModel()
{
    m_jobTimeoutTimer.stop();
    if (m_process.state() != QProcess::NotRunning) {
        m_process.kill();
        m_process.waitForFinished(1000);
    }
}

bool AiTranscriptionModel::busy() const
{
    return m_busy;
}

bool AiTranscriptionModel::completed() const
{
    return m_completed;
}

QString AiTranscriptionModel::statusText() const
{
    return m_statusText;
}

QString AiTranscriptionModel::logText() const
{
    return m_logText;
}

QString AiTranscriptionModel::inputSummary() const
{
    return m_inputSummary;
}

QString AiTranscriptionModel::outputPath() const
{
    return m_outputPath;
}

QString AiTranscriptionModel::sourceKind() const
{
    return m_sourceKind;
}

QVariantMap AiTranscriptionModel::report() const
{
    return m_report;
}

bool AiTranscriptionModel::reviewRequired() const
{
    return m_reviewRequired;
}

QString AiTranscriptionModel::reviewProjectPath() const
{
    return m_reviewProjectPath;
}

QVariantList AiTranscriptionModel::reviewMeasures() const
{
    return m_reviewMeasures;
}

QVariantList AiTranscriptionModel::reviewPages() const
{
    return m_reviewPages;
}

int AiTranscriptionModel::reviewedMeasureCount() const
{
    return m_reviewedMeasureCount;
}

int AiTranscriptionModel::reviewMeasureCount() const
{
    return m_reviewMeasureCount;
}

int AiTranscriptionModel::selectedReviewMeasure() const
{
    return m_selectedReviewMeasure;
}

int AiTranscriptionModel::selectedReviewMeasureLength() const
{
    return m_selectedReviewMeasureLength;
}

QVariantList AiTranscriptionModel::selectedReviewEvents() const
{
    return m_selectedReviewEvents;
}

QVariantList AiTranscriptionModel::selectedReviewRests() const
{
    return m_selectedReviewRests;
}

QVariantList AiTranscriptionModel::selectedReviewVisualErrors() const
{
    return m_selectedReviewVisualErrors;
}

QString AiTranscriptionModel::selectedReviewSourceCrop() const
{
    return m_selectedReviewSourceCrop;
}

bool AiTranscriptionModel::startMidi(
    const QString& inputPath,
    const QString& outputPath,
    const QString& grid,
    const QString& bpmMode,
    const QString& bpmValue,
    const QString& startShift,
    int leadingMeasures)
{
    const QString input = localPathFromInput(inputPath);
    const QString output = localPathFromInput(outputPath);
    if (busy()) {
        return false;
    }
    if (!QFileInfo::exists(input)
        || (!input.endsWith(".mid", Qt::CaseInsensitive)
            && !input.endsWith(".midi", Qt::CaseInsensitive))) {
        setStatusText(tr("请选择有效的 .mid 或 .midi 文件"));
        return false;
    }
    if (!output.endsWith(".db", Qt::CaseInsensitive)) {
        setStatusText(tr("输出文件必须使用 .db 扩展名"));
        return false;
    }
    if (leadingMeasures < 0 || leadingMeasures > 8) {
        setStatusText(tr("前置休止小节必须在 0 到 8 之间"));
        return false;
    }
    const QString converter = resolveMidiConverter();
    if (converter.isEmpty()) {
        setStatusText(tr("找不到 MIDI 标准化器，请检查安装是否完整"));
        return false;
    }
    const QString bpm = normalizedBpm(bpmMode, bpmValue);
    if (bpm.isEmpty()) {
        setStatusText(tr("请输入 30 到 300 之间的 BPM"));
        return false;
    }

    m_jobDir = std::make_unique<QTemporaryDir>(
        QDir::tempPath() + "/dbscore-ai-transcription-XXXXXX");
    if (!m_jobDir->isValid()) {
        setStatusText(tr("无法创建临时工作目录"));
        return false;
    }
    m_reportPath = m_jobDir->filePath("report.json");
    startJob(
        {
            "-u",
            resolveEngine(),
            "midi",
            "--input",
            input,
            "--output",
            output,
            "--converter",
            converter,
            "--style",
            resolveStyle(),
            "--grid",
            grid,
            "--bpm",
            bpm,
            "--start-shift",
            startShift,
            "--leading-measures",
            QString::number(leadingMeasures),
            "--report",
            m_reportPath,
        },
        "midi");
    setInputSummary(QFileInfo(input).fileName());
    setOutputPath(output);
    setSourceKind("midi");
    return true;
}

bool AiTranscriptionModel::startImages(
    const QVariantList& inputPaths,
    const QString& outputPath,
    const QString& title,
    int tempo)
{
    const QString output = localPathFromInput(outputPath);
    if (busy()) {
        return false;
    }
    if (inputPaths.isEmpty()) {
        setStatusText(tr("请选择至少一张鼓谱图片或 PDF"));
        return false;
    }
    if (!output.endsWith(".db", Qt::CaseInsensitive)) {
        setStatusText(tr("输出文件必须使用 .db 扩展名"));
        return false;
    }
    if (title.trimmed().isEmpty()) {
        setStatusText(tr("请输入曲名"));
        return false;
    }
    if (tempo < 20 || tempo > 400) {
        setStatusText(tr("BPM 必须在 20 到 400 之间"));
        return false;
    }
    for (const QVariant& value : inputPaths) {
        const QString path = localPathFromInput(value.toString());
        if (!QFileInfo::exists(path)) {
            setStatusText(tr("找不到源文件：%1。请重新选择图片或 PDF。").arg(path));
            return false;
        }
    }
    const QString audiveris = resolveAudiveris();
    if (audiveris.isEmpty()) {
        setStatusText(tr("找不到 Audiveris OMR 引擎，请检查安装路径"));
        return false;
    }

    m_jobDir = std::make_unique<QTemporaryDir>(
        QDir::tempPath() + "/dbscore-ai-transcription-XXXXXX");
    if (!m_jobDir->isValid()) {
        setStatusText(tr("无法创建临时工作目录"));
        return false;
    }
    m_reportPath = m_jobDir->filePath("report.json");

    QStringList arguments = {
        "-u",
        resolveEngine(),
        "image",
        "--output",
        output,
        "--title",
        title,
        "--tempo",
        QString::number(tempo),
        "--audiveris",
        audiveris,
        "--dbscore",
        applicationExecutable(),
        "--style",
        resolveStyle(),
        "--pdftoppm",
        resolvePdfToPpm(),
        "--report",
        m_reportPath,
    };
    for (const QVariant& path : inputPaths) {
        arguments << "--input" << localPathFromInput(path.toString());
    }
    startJob(arguments, "image");
    setInputSummary(inputPaths.size() == 1
                    ? QFileInfo(localPathFromInput(inputPaths.first().toString())).fileName()
                    : tr("%1 个页面").arg(inputPaths.size()));
    setOutputPath(output);
    setSourceKind("image");
    return true;
}

bool AiTranscriptionModel::setMeasureReviewed(int number, bool reviewed)
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    bool changed = false;
    for (int index = 0; index < m_reviewMeasures.size(); ++index) {
        QVariantMap measure = m_reviewMeasures[index].toMap();
        if (measure.value("number").toInt() != number) {
            continue;
        }
        if (measure.value("reviewed").toBool() == reviewed) {
            return true;
        }
        measure["reviewed"] = reviewed;
        m_reviewMeasures[index] = measure;
        changed = true;
        break;
    }
    if (!changed) {
        return false;
    }
    m_reviewedMeasureCount = 0;
    for (const QVariant& value : m_reviewMeasures) {
        if (value.toMap().value("reviewed").toBool()) {
            ++m_reviewedMeasureCount;
        }
    }
    m_reviewData["measures"] = m_reviewMeasures;
    if (!saveReview()) {
        setStatusText(tr("无法保存小节复核状态"));
        return false;
    }
    emit reviewStateChanged();
    setStatusText(
        tr("已完成 %1 / %2 个小节复核")
            .arg(m_reviewedMeasureCount)
            .arg(m_reviewMeasureCount));
    return true;
}

bool AiTranscriptionModel::markAllMeasuresReviewed()
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    bool changed = false;
    for (int index = 0; index < m_reviewMeasures.size(); ++index) {
        QVariantMap measure = m_reviewMeasures[index].toMap();
        if (!measure.value("reviewed").toBool()) {
            measure["reviewed"] = true;
            m_reviewMeasures[index] = measure;
            changed = true;
        }
    }
    if (!changed) {
        return true;
    }
    m_reviewedMeasureCount = m_reviewMeasureCount;
    m_reviewData["measures"] = m_reviewMeasures;
    if (!saveReview()) {
        setStatusText(tr("无法保存小节复核状态"));
        return false;
    }
    emit reviewStateChanged();
    setStatusText(tr("已将全部 %1 个小节标记为已复核").arg(m_reviewMeasureCount));
    return true;
}

void AiTranscriptionModel::selectReviewMeasure(int number)
{
    m_selectedReviewMeasure = number;
    m_selectedReviewEvents.clear();
    m_selectedReviewRests.clear();
    m_selectedReviewVisualErrors.clear();
    m_selectedReviewSourceCrop.clear();
    for (const QVariant& value : m_reviewMeasures) {
        const QVariantMap measure = value.toMap();
        if (measure.value("number").toInt() == number) {
            m_selectedReviewEvents = measure.value("events").toList();
            m_selectedReviewRests = measure.value("rests").toList();
            m_selectedReviewVisualErrors =
                measure.value("visualErrors").toList();
            m_selectedReviewSourceCrop =
                measure.value("sourceCrop").toString();
            m_selectedReviewMeasureLength = measure.value("length").toInt();
            break;
        }
    }
    emit reviewStateChanged();
}

bool AiTranscriptionModel::updateReviewEvent(
    int measureNumber,
    int eventIndex,
    const QString& time,
    const QString& pitches)
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    QVariantList events;
    int measureLength = 0;
    for (const QVariant& value : m_reviewMeasures) {
        const QVariantMap measure = value.toMap();
        if (measure.value("number").toInt() == measureNumber) {
            events = measure.value("events").toList();
            measureLength = measure.value("length").toInt();
            break;
        }
    }
    if (eventIndex < 0 || eventIndex >= events.size()) {
        setStatusText(tr("要修改的音符不存在"));
        return false;
    }
    QVariantMap event;
    if (!parseReviewEvent(time, pitches, measureLength, &event)) {
        return false;
    }
    const QVariantMap previous = events[eventIndex].toMap();
    event["articulations"] = previous.value("articulations").toList();
    events[eventIndex] = event;
    return applyReviewEvents(measureNumber, events);
}

bool AiTranscriptionModel::addReviewEvent(
    int measureNumber,
    const QString& time,
    const QString& pitches)
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    QVariantList events;
    int measureLength = 0;
    for (const QVariant& value : m_reviewMeasures) {
        const QVariantMap measure = value.toMap();
        if (measure.value("number").toInt() == measureNumber) {
            events = measure.value("events").toList();
            measureLength = measure.value("length").toInt();
            break;
        }
    }
    QVariantMap event;
    if (!parseReviewEvent(time, pitches, measureLength, &event)) {
        return false;
    }
    events.append(event);
    return applyReviewEvents(measureNumber, events);
}

bool AiTranscriptionModel::deleteReviewEvent(int measureNumber, int eventIndex)
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    QVariantList events;
    for (const QVariant& value : m_reviewMeasures) {
        const QVariantMap measure = value.toMap();
        if (measure.value("number").toInt() == measureNumber) {
            events = measure.value("events").toList();
            break;
        }
    }
    if (eventIndex < 0 || eventIndex >= events.size()) {
        setStatusText(tr("要删除的音符不存在"));
        return false;
    }
    events.removeAt(eventIndex);
    return applyReviewEvents(measureNumber, events);
}

bool AiTranscriptionModel::updateReviewRest(
    int measureNumber,
    int restIndex,
    const QString& time,
    const QString& voice,
    const QString& duration)
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    QVariantList rests;
    int measureLength = 0;
    for (const QVariant& value : m_reviewMeasures) {
        const QVariantMap measure = value.toMap();
        if (measure.value("number").toInt() == measureNumber) {
            rests = measure.value("rests").toList();
            measureLength = measure.value("length").toInt();
            break;
        }
    }
    if (restIndex < 0 || restIndex >= rests.size()) {
        setStatusText(tr("要修改的休止符不存在"));
        return false;
    }
    QVariantMap rest;
    if (!parseReviewRest(time, voice, duration, measureLength, &rest)) {
        return false;
    }
    rests[restIndex] = rest;
    return applyReviewRests(measureNumber, rests);
}

bool AiTranscriptionModel::addReviewRest(
    int measureNumber,
    const QString& time,
    const QString& voice,
    const QString& duration)
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    QVariantList rests;
    int measureLength = 0;
    for (const QVariant& value : m_reviewMeasures) {
        const QVariantMap measure = value.toMap();
        if (measure.value("number").toInt() == measureNumber) {
            rests = measure.value("rests").toList();
            measureLength = measure.value("length").toInt();
            break;
        }
    }
    QVariantMap rest;
    if (!parseReviewRest(time, voice, duration, measureLength, &rest)) {
        return false;
    }
    rests.append(rest);
    return applyReviewRests(measureNumber, rests);
}

bool AiTranscriptionModel::deleteReviewRest(int measureNumber, int restIndex)
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    QVariantList rests;
    for (const QVariant& value : m_reviewMeasures) {
        const QVariantMap measure = value.toMap();
        if (measure.value("number").toInt() == measureNumber) {
            rests = measure.value("rests").toList();
            break;
        }
    }
    if (restIndex < 0 || restIndex >= rests.size()) {
        setStatusText(tr("要删除的休止符不存在"));
        return false;
    }
    rests.removeAt(restIndex);
    return applyReviewRests(measureNumber, rests);
}

bool AiTranscriptionModel::reflowReviewMeasure(int measureNumber)
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    QVariantList events;
    for (const QVariant& value : m_reviewMeasures) {
        const QVariantMap measure = value.toMap();
        if (measure.value("number").toInt() == measureNumber) {
            events = measure.value("events").toList();
            break;
        }
    }
    for (QVariant& value : events) {
        QVariantMap event = value.toMap();
        QVariantList parts;
        for (const QVariant& partValue : event.value("parts").toList()) {
            QVariantMap part = partValue.toMap();
            part["duration"] = QVariant();
            part["dots"] = 0;
            part["beams"] = 0;
            part["beam_group"] = QVariant();
            parts.append(part);
        }
        event["parts"] = parts;
        event["review"] = false;
        event["review_resolution"] = "manual-duration-reflow";
        event["time_verified"] = true;
        value = event;
    }
    return applyReviewEvents(measureNumber, events);
}

bool AiTranscriptionModel::updateReviewMeasureLength(int measureNumber, int beats)
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    if (beats < 1 || beats > 16) {
        setStatusText(tr("拍数必须在 1 到 16 之间"));
        return false;
    }
    for (int index = 0; index < m_reviewMeasures.size(); ++index) {
        QVariantMap measure = m_reviewMeasures[index].toMap();
        if (measure.value("number").toInt() != measureNumber) {
            continue;
        }
        measure["length"] = beats;
        measure["visualErrors"] = QVariantList();
        measure["reviewed"] = false;
        m_selectedReviewMeasureLength = beats;
        m_reviewMeasures[index] = measure;
        m_reviewData["measures"] = m_reviewMeasures;
        m_reviewedMeasureCount = 0;
        for (const QVariant& value : m_reviewMeasures) {
            if (value.toMap().value("reviewed").toBool()) {
                ++m_reviewedMeasureCount;
            }
        }
        if (!saveReview()) {
            setStatusText(tr("无法保存拍号修正"));
            return false;
        }
        emit reviewStateChanged();
        setStatusText(
            tr("第 %1 小节已设为 %2/4，请重新核对拍位")
                .arg(measureNumber)
                .arg(beats));
        return true;
    }
    return false;
}

bool AiTranscriptionModel::finalizeImageReview()
{
    if (busy() || !reviewRequired()) {
        return false;
    }
    if (m_reviewMeasureCount <= 0) {
        setStatusText(tr("复核工程中没有可生成的小节"));
        return false;
    }
    if (m_reviewedMeasureCount != m_reviewMeasureCount) {
        setStatusText(tr("必须完成全部小节复核后才能生成正式鼓谱"));
        return false;
    }
    if (resolveEngine().isEmpty() || resolvePython().isEmpty()) {
        setStatusText(tr("AI 转谱引擎不完整"));
        return false;
    }
    m_jobDir = std::make_unique<QTemporaryDir>(
        QDir::tempPath() + "/dbscore-ai-finalize-XXXXXX");
    if (!m_jobDir->isValid()) {
        setStatusText(tr("无法创建临时工作目录"));
        return false;
    }
    m_reportPath = m_jobDir->filePath("report.json");
    setSourceKind("image-review");
    startJob(
        {
            "-u",
            resolveEngine(),
            "review-finalize",
            "--project",
            m_reviewProjectPath,
            "--pdftoppm",
            resolvePdfToPpm(),
            "--report",
            m_reportPath,
        },
        "image-review");
    setStatusText(tr("全部小节已确认，正在生成正式鼓谱…"));
    return true;
}

bool AiTranscriptionModel::loadReviewProject(const QString& projectPath)
{
    if (busy()) {
        return false;
    }
    const QString path = localPathFromInput(projectPath);
    const QFileInfo info(path);
    const QString reviewPath = info.isDir()
                               ? QDir(path).filePath("review.json")
                               : path;
    if (!QFileInfo::exists(reviewPath)) {
        setStatusText(tr("所选目录中没有 review.json"));
        return false;
    }
    if (!loadReview(QVariantMap { { "reviewPath", reviewPath } })) {
        return false;
    }
    setSourceKind("image");
    setOutputPath(m_reviewData.value("finalOutput").toString());
    setInputSummary(
        tr("%1 个小节的复核工程").arg(m_reviewMeasureCount));
    setStatusText(
        tr("已载入复核工程，已完成 %1 / %2 个小节")
            .arg(m_reviewedMeasureCount)
            .arg(m_reviewMeasureCount));
    return true;
}

void AiTranscriptionModel::cancel()
{
    if (!busy()) {
        return;
    }
    m_jobTimeoutTimer.stop();
    const int generation = m_processGeneration;
    m_cancelRequested = true;
    m_timeoutRequested = false;
    setStatusText(tr("正在停止转换任务…"));
    m_process.terminate();
    QTimer::singleShot(3000, this, [this, generation]() {
        if (generation == m_processGeneration
            && m_process.state() != QProcess::NotRunning) {
            m_process.kill();
        }
    });
}

void AiTranscriptionModel::reset()
{
    m_jobTimeoutTimer.stop();
    if (busy()) {
        cancel();
    }
    setCompleted(false);
    setStatusText(QString());
    appendLog(QString());
    setInputSummary(QString());
    setOutputPath(QString());
    setSourceKind(QString());
    setReport({});
    clearReviewState();
    m_reportPath.clear();
}

void AiTranscriptionModel::clearReviewState()
{
    m_reviewRequired = false;
    m_reviewProjectPath.clear();
    m_reviewPath.clear();
    m_reviewData.clear();
    m_reviewMeasures.clear();
    m_reviewPages.clear();
    m_selectedReviewEvents.clear();
    m_selectedReviewRests.clear();
    m_selectedReviewVisualErrors.clear();
    m_reviewedMeasureCount = 0;
    m_reviewMeasureCount = 0;
    m_selectedReviewMeasure = 0;
    m_selectedReviewMeasureLength = 4;
    emit reviewStateChanged();
}

void AiTranscriptionModel::showError(const QString& message)
{
    setCompleted(false);
    setStatusText(message);
}

bool AiTranscriptionModel::openOutputInScore()
{
    const QFileInfo info(outputPath());
    if (!info.exists() || !info.isFile()) {
        setStatusText(tr("输出文件不存在"));
        return false;
    }
    if (!completed() || info.suffix().compare("db", Qt::CaseInsensitive) != 0) {
        setStatusText(tr("请等待正式 .db 鼓谱生成完成后再编辑"));
        return false;
    }

    setStatusText(tr("正在打开乐谱…"));
    dispatcher()->dispatch(
        "file-open",
        ActionData::make_arg2<QUrl, QString>(
            QUrl::fromLocalFile(info.absoluteFilePath()),
            info.completeBaseName()));
    return true;
}

void AiTranscriptionModel::revealOutput()
{
    const QFileInfo info(outputPath());
    if (!info.exists()) {
        setStatusText(tr("输出文件不存在"));
        return;
    }
    QDesktopServices::openUrl(QUrl::fromLocalFile(info.absolutePath()));
}

void AiTranscriptionModel::revealReviewProject()
{
    if (m_reviewProjectPath.isEmpty()
        || !QFileInfo(m_reviewProjectPath).isDir()) {
        setStatusText(tr("复核工程目录不存在"));
        return;
    }
    QDesktopServices::openUrl(QUrl::fromLocalFile(m_reviewProjectPath));
}

QString AiTranscriptionModel::environmentDiagnostics() const
{
    const auto line = [](const QString& label, const QString& path) {
        return QString("%1: %2 [%3]")
            .arg(label, path.isEmpty() ? tr("未找到") : path,
                 QFileInfo::exists(path) ? tr("可用") : tr("不可用"));
    };
    return QStringList {
        line(tr("Python"), resolvePython()),
        line(tr("转换引擎"), resolveEngine()),
        line(tr("MIDI 标准化器"), resolveMidiConverter()),
        line(tr("DB绘谱样式"), resolveStyle()),
        line(tr("PDF 渲染器"), resolvePdfToPpm()),
        line(tr("Audiveris"), resolveAudiveris()),
    }.join('\n');
}

QString AiTranscriptionModel::normalizeInputPath(const QString& path) const
{
    return localPathFromInput(path);
}

QString AiTranscriptionModel::localFileUrl(const QString& path) const
{
    const QString localPath = localPathFromInput(path);
    return localPath.isEmpty()
           ? QString()
           : QUrl::fromLocalFile(localPath).toString(QUrl::FullyEncoded);
}

void AiTranscriptionModel::startJob(const QStringList& arguments, const QString& kind)
{
    const QString python = resolvePython();
    const QString engine = resolveEngine();
    if (python.isEmpty() || engine.isEmpty()) {
        setStatusText(tr("AI 转谱引擎不完整，请运行环境检查"));
        return;
    }

    if (kind != "image-review") {
        clearReviewState();
    }

    m_jobTimeoutTimer.stop();
    ++m_processGeneration;
    setBusy(true);
    setCompleted(false);
    setReport({});
    m_cancelRequested = false;
    m_timeoutRequested = false;
    m_statusBuffer.clear();
    appendLog(QString());
    setStatusText(kind == "midi"
                  ? tr("正在准备 MIDI 转谱…")
                  : tr("正在准备图片 / PDF 分析…"));

    QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
    environment.insert("PYTHONUNBUFFERED", "1");
    const QString pythonHome = pythonHomeFor(python);
    if (!pythonHome.isEmpty()) {
        environment.insert("PYTHONHOME", pythonHome);
        environment.insert("PYTHONNOUSERSITE", "1");
    }
    m_process.setProcessEnvironment(environment);
    m_process.setWorkingDirectory(m_jobDir->path());
    m_process.start(python, arguments);
    m_jobTimeoutTimer.start(jobTimeoutMilliseconds());
}

void AiTranscriptionModel::readProcessOutput()
{
    const QString text = QString::fromUtf8(m_process.readAllStandardOutput());
    if (text.isEmpty()) {
        return;
    }
    m_statusBuffer += text;
    while (m_statusBuffer.contains('\n')) {
        const int newline = m_statusBuffer.indexOf('\n');
        const QString line = m_statusBuffer.left(newline);
        m_statusBuffer.remove(0, newline + 1);
        if (line.startsWith("STAGE|")) {
            setStatusText(line.mid(6));
        } else if (line.startsWith("ERROR|")) {
            setStatusText(line.mid(6));
        } else if (!line.startsWith("RUN|")) {
            appendLog(line);
        }
    }
}

void AiTranscriptionModel::finishJob(
    int exitCode,
    QProcess::ExitStatus exitStatus)
{
    m_jobTimeoutTimer.stop();
    readProcessOutput();
    if (!m_statusBuffer.trimmed().isEmpty()) {
        if (m_statusBuffer.startsWith("STAGE|")) {
            setStatusText(m_statusBuffer.mid(6).trimmed());
        } else if (m_statusBuffer.startsWith("ERROR|")) {
            setStatusText(m_statusBuffer.mid(6).trimmed());
        } else {
            appendLog(m_statusBuffer);
        }
        m_statusBuffer.clear();
    }

    QVariantMap parsedReport;
    QFile reportFile(m_reportPath);
    if (reportFile.open(QIODevice::ReadOnly)) {
        const QJsonDocument document = QJsonDocument::fromJson(reportFile.readAll());
        if (document.isObject()) {
            parsedReport = document.object().toVariantMap();
        }
    }
    setReport(parsedReport);

    const bool processSucceeded = exitStatus == QProcess::NormalExit && exitCode == 0;
    if (m_timeoutRequested) {
        setBusy(false);
        setCompleted(false);
        setStatusText(tr("转谱超时，任务已停止。请检查源文件或环境后重试"));
        return;
    }

    if (processSucceeded && parsedReport.value("reviewRequired").toBool()) {
        setBusy(false);
        setCompleted(false);
        if (!loadReview(parsedReport)) {
            setStatusText(tr("识别已完成，但无法载入逐小节复核数据"));
            return;
        }
        const int unresolved = parsedReport.value(
            "unresolvedTotal",
            parsedReport.value("unresolvedEvents")).toInt();
        setStatusText(
            tr("识别完成：请逐小节核对 %1 个；其中 %2 个记号需要确认。"
               "勾选每行左侧复选框后，点击“生成正式鼓谱”")
                .arg(m_reviewMeasureCount)
                .arg(unresolved));
        return;
    }

    const bool reportSucceeded = parsedReport.value("valid").toBool();
    const QFileInfo outputInfo(outputPath());
    const bool outputExists = outputInfo.exists()
                              && outputInfo.isFile()
                              && outputInfo.size() > 0;
    const bool success = processSucceeded && reportSucceeded && outputExists
                         && !m_cancelRequested;

    setBusy(false);
    if (success) {
        if (sourceKind() == "image-review") {
            m_reviewRequired = false;
            emit reviewStateChanged();
        }
        setCompleted(true);
        setStatusText(sourceKind() == "midi"
                      ? tr("转换完成：MIDI 逐事件时间轴完全一致")
                      : tr("转换完成：全部严格校验通过"));
        return;
    }
    setCompleted(false);
    if (m_reviewRequired && !m_reviewPath.isEmpty()) {
        (void)loadReview(QVariantMap { { "reviewPath", m_reviewPath } });
    }
    if (m_cancelRequested) {
        setStatusText(tr("转换任务已停止"));
    } else if (!parsedReport.isEmpty() && parsedReport.contains("error")) {
        setStatusText(localizedJobError(parsedReport.value("error").toString()));
    } else if (exitStatus == QProcess::CrashExit) {
        setStatusText(tr("转换引擎异常退出，请查看日志后重试"));
    } else if (exitCode != 0) {
        setStatusText(tr("转换失败（退出码 %1）").arg(exitCode));
    } else if (!reportSucceeded) {
        setStatusText(tr("转换结果未通过严格校验"));
    } else if (!outputExists) {
        setStatusText(tr("转换结束后没有生成有效的 .db 文件"));
    } else {
        setStatusText(tr("转换失败，请查看日志后重试"));
    }
}

void AiTranscriptionModel::setBusy(bool value)
{
    if (m_busy == value) {
        return;
    }
    m_busy = value;
    emit busyChanged();
}

void AiTranscriptionModel::setCompleted(bool value)
{
    if (m_completed == value) {
        return;
    }
    m_completed = value;
    emit completedChanged();
}

void AiTranscriptionModel::setStatusText(const QString& value)
{
    if (m_statusText == value) {
        return;
    }
    m_statusText = value;
    emit statusTextChanged();
}

void AiTranscriptionModel::appendLog(const QString& value)
{
    if (value.isEmpty()) {
        m_logText.clear();
        emit logTextChanged();
        return;
    }
    if (!m_logText.isEmpty()) {
        m_logText += '\n';
    }
    m_logText += value;
    emit logTextChanged();
}

void AiTranscriptionModel::setInputSummary(const QString& value)
{
    if (m_inputSummary == value) {
        return;
    }
    m_inputSummary = value;
    emit inputSummaryChanged();
}

void AiTranscriptionModel::setOutputPath(const QString& value)
{
    if (m_outputPath == value) {
        return;
    }
    m_outputPath = value;
    emit outputPathChanged();
}

void AiTranscriptionModel::setSourceKind(const QString& value)
{
    if (m_sourceKind == value) {
        return;
    }
    m_sourceKind = value;
    emit sourceKindChanged();
}

void AiTranscriptionModel::setReport(const QVariantMap& value)
{
    if (m_report == value) {
        return;
    }
    m_report = value;
    emit reportChanged();
}

bool AiTranscriptionModel::loadReview(const QVariantMap& report)
{
    const QString path = report.value("reviewPath").toString();
    QFile file(path);
    if (path.isEmpty() || !file.open(QIODevice::ReadOnly)) {
        setStatusText(tr("无法读取逐小节复核数据"));
        return false;
    }
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll());
    if (!document.isObject()) {
        setStatusText(tr("逐小节复核数据格式错误"));
        return false;
    }
    m_reviewPath = path;
    m_reviewData = document.object().toVariantMap();
    m_reviewProjectPath = m_reviewData.value("projectDir").toString();
    m_reviewMeasures = m_reviewData.value("measures").toList();
    m_reviewMeasureCount = m_reviewMeasures.size();
    m_reviewedMeasureCount = 0;
    for (const QVariant& value : m_reviewMeasures) {
        if (value.toMap().value("reviewed").toBool()) {
            ++m_reviewedMeasureCount;
        }
    }
    if (m_reviewMeasureCount > 0) {
        m_selectedReviewMeasure =
            m_reviewMeasures.first().toMap().value("number").toInt();
        m_selectedReviewMeasureLength =
            m_reviewMeasures.first().toMap().value("length").toInt();
        m_selectedReviewEvents =
            m_reviewMeasures.first().toMap().value("events").toList();
        m_selectedReviewRests =
            m_reviewMeasures.first().toMap().value("rests").toList();
        m_selectedReviewVisualErrors =
            m_reviewMeasures.first().toMap().value("visualErrors").toList();
        m_selectedReviewSourceCrop =
            m_reviewMeasures.first().toMap().value("sourceCrop").toString();
    }

    const QVariantList originalPages =
        m_reviewData.value("originalPages").toList();
    const QVariantList generatedPages =
        m_reviewData.value("generatedPages").toList();
    const QVariantList pageMeasures =
        m_reviewData.value("pageMeasureNumbers").toList();
    m_reviewPages.clear();
    const int pageCount = std::max(
        originalPages.size(),
        generatedPages.size());
    for (int index = 0; index < pageCount; ++index) {
        const QVariantList numbers =
            index < pageMeasures.size() ? pageMeasures[index].toList() : QVariantList();
        m_reviewPages.append(QVariantMap {
            { "page", index + 1 },
            { "original", index < originalPages.size()
                              ? originalPages[index].toString()
                              : QString() },
            { "generated", index < generatedPages.size()
                               ? generatedPages[index].toString()
                               : QString() },
            { "firstMeasure", numbers.isEmpty()
                                  ? 0
                                  : numbers.first().toInt() },
            { "lastMeasure", numbers.isEmpty()
                                 ? 0
                                 : numbers.last().toInt() },
        });
    }
    m_reviewRequired = true;
    emit reviewStateChanged();
    return true;
}

bool AiTranscriptionModel::saveReview()
{
    if (m_reviewPath.isEmpty()) {
        return false;
    }
    QSaveFile file(m_reviewPath);
    if (!file.open(QIODevice::WriteOnly)) {
        return false;
    }
    file.write(
        QJsonDocument::fromVariant(m_reviewData)
            .toJson(QJsonDocument::Indented));
    return file.commit();
}

bool AiTranscriptionModel::applyReviewEvents(
    int measureNumber,
    const QVariantList& events)
{
    QVariantList sortedEvents = events;
    std::sort(
        sortedEvents.begin(),
        sortedEvents.end(),
        [](const QVariant& left, const QVariant& right) {
            bool leftOk = false;
            bool rightOk = false;
            const double leftValue = fractionValue(
                left.toMap().value("time").toString(),
                &leftOk);
            const double rightValue = fractionValue(
                right.toMap().value("time").toString(),
                &rightOk);
            if (!leftOk || !rightOk) {
                return leftOk;
            }
            return leftValue < rightValue;
        });
    for (int index = 0; index < m_reviewMeasures.size(); ++index) {
        QVariantMap measure = m_reviewMeasures[index].toMap();
        if (measure.value("number").toInt() != measureNumber) {
            continue;
        }
        QVariantList unresolvedEvents;
        for (const QVariant& value : sortedEvents) {
            const QVariantMap event = value.toMap();
            if (event.value("review").toBool()) {
                unresolvedEvents.append(QVariantMap {
                    { "time", event.value("time") },
                    { "pitches", event.value("pitches") },
                    { "reason", event.value(
                                    "review_resolution",
                                    "unconfirmed-rhythm") },
                });
            }
        }
        measure["events"] = sortedEvents;
        measure["unresolvedEvents"] = unresolvedEvents;
        measure["unresolvedCount"] =
            unresolvedEvents.size()
            + measure.value("unresolvedRests").toList().size();
        measure["visualErrors"] = QVariantList();
        measure["reviewed"] = false;
        m_reviewMeasures[index] = measure;
        if (m_selectedReviewMeasure == measureNumber) {
            m_selectedReviewEvents = sortedEvents;
        }
        break;
    }
    m_reviewData["measures"] = m_reviewMeasures;
    m_reviewedMeasureCount = 0;
    for (const QVariant& value : m_reviewMeasures) {
        if (value.toMap().value("reviewed").toBool()) {
            ++m_reviewedMeasureCount;
        }
    }
    if (!saveReview()) {
        setStatusText(tr("无法保存音符修正"));
        return false;
    }
    emit reviewStateChanged();
    setStatusText(
        tr("第 %1 小节已更新，请重新核对后勾选确认")
            .arg(measureNumber));
    return true;
}

bool AiTranscriptionModel::applyReviewRests(
    int measureNumber,
    const QVariantList& rests)
{
    QVariantList sortedRests = rests;
    std::sort(
        sortedRests.begin(),
        sortedRests.end(),
        [](const QVariant& left, const QVariant& right) {
            bool leftOk = false;
            bool rightOk = false;
            const double leftValue = fractionValue(
                left.toMap().value("time").toString(),
                &leftOk);
            const double rightValue = fractionValue(
                right.toMap().value("time").toString(),
                &rightOk);
            if (!leftOk || !rightOk) {
                return leftOk;
            }
            return leftValue < rightValue;
        });
    for (int index = 0; index < m_reviewMeasures.size(); ++index) {
        QVariantMap measure = m_reviewMeasures[index].toMap();
        if (measure.value("number").toInt() != measureNumber) {
            continue;
        }
        QVariantList unresolvedRests;
        for (const QVariant& value : sortedRests) {
            const QVariantMap rest = value.toMap();
            if (rest.value("review").toBool()) {
                unresolvedRests.append(rest);
            }
        }
        measure["rests"] = sortedRests;
        measure["unresolvedRests"] = unresolvedRests;
        measure["unresolvedCount"] =
            measure.value("unresolvedEvents").toList().size()
            + unresolvedRests.size();
        measure["visualErrors"] = QVariantList();
        measure["reviewed"] = false;
        m_reviewMeasures[index] = measure;
        if (m_selectedReviewMeasure == measureNumber) {
            m_selectedReviewRests = sortedRests;
        }
        break;
    }
    m_reviewData["measures"] = m_reviewMeasures;
    m_reviewedMeasureCount = 0;
    for (const QVariant& value : m_reviewMeasures) {
        if (value.toMap().value("reviewed").toBool()) {
            ++m_reviewedMeasureCount;
        }
    }
    if (!saveReview()) {
        setStatusText(tr("无法保存休止符修正"));
        return false;
    }
    emit reviewStateChanged();
    setStatusText(
        tr("第 %1 小节休止符已更新，请重新核对后勾选确认")
            .arg(measureNumber));
    return true;
}

QVariantMap AiTranscriptionModel::buildReviewEvent(
    const QString& time,
    const QStringList& pitches) const
{
    QVariantList upperPitches;
    QVariantList lowerPitches;
    QVariantList allPitches;
    static const QSet<int> lowerDrums { 35, 36, 44 };
    for (const QString& text : pitches) {
        const int pitch = text.toInt();
        allPitches.append(pitch);
        (lowerDrums.contains(pitch) ? lowerPitches : upperPitches)
            .append(pitch);
    }
    QVariantList parts;
    const auto addPart = [&parts](
                             const QString& voice,
                             const QVariantList& partPitches) {
        if (partPitches.isEmpty()) {
            return;
        }
        parts.append(QVariantMap {
            { "voice", voice },
            { "pitches", partPitches },
            { "duration", QVariant() },
            { "dots", 0 },
            { "beams", 0 },
            { "beam_group", QVariant() },
        });
    };
    addPart("up", upperPitches);
    addPart("down", lowerPitches);
    const double timeValue = fractionValue(time);
    return QVariantMap {
        { "time", time.trimmed() },
        { "x", timeValue * 1000.0 },
        { "rhythm_x", timeValue * 1000.0 },
        { "pitches", allPitches },
        { "parts", parts },
        { "articulations", QVariantList() },
        { "review", false },
        { "review_resolution", "manual-review" },
        { "time_verified", true },
        { "source", "manual-review" },
    };
}

bool AiTranscriptionModel::parseReviewEvent(
    const QString& time,
    const QString& pitches,
    int measureLength,
    QVariantMap* event)
{
    bool timeOk = false;
    const double timeValue = fractionValue(time, &timeOk);
    if (!timeOk || timeValue < 0 || timeValue >= measureLength / 4.0) {
        setStatusText(tr("拍位无效，请使用如 0、1/16、1/8、3/16 的写法"));
        return false;
    }
    QString normalizedPitches = pitches;
    normalizedPitches.replace(QStringLiteral("，"), QStringLiteral(","));
    const QStringList pitchTexts =
        normalizedPitches.split(',', Qt::SkipEmptyParts);
    if (pitchTexts.isEmpty()) {
        setStatusText(tr("鼓件不能为空"));
        return false;
    }
    QStringList result;
    for (const QString& text : pitchTexts) {
        bool ok = false;
        const int pitch = text.trimmed().toInt(&ok);
        if (!ok || pitch < 35 || pitch > 87) {
            setStatusText(tr("鼓件音高必须是 35–87 的 GM 鼓件"));
            return false;
        }
        result.append(QString::number(pitch));
    }
    result.removeDuplicates();
    result.sort();
    *event = buildReviewEvent(time, result);
    return true;
}

bool AiTranscriptionModel::parseReviewRest(
    const QString& time,
    const QString& voice,
    const QString& duration,
    int measureLength,
    QVariantMap* rest)
{
    bool timeOk = false;
    const double timeValue = fractionValue(time, &timeOk);
    if (!timeOk || timeValue < 0 || timeValue >= measureLength / 4.0) {
        setStatusText(tr("休止符拍位无效"));
        return false;
    }
    if (voice != "up" && voice != "down") {
        setStatusText(tr("休止符声部必须是 up 或 down"));
        return false;
    }
    static const QSet<QString> durations {
        "whole",
        "half",
        "quarter",
        "eighth",
        "16th",
        "32nd",
        "64th",
    };
    if (!durations.contains(duration)) {
        setStatusText(tr("不支持的休止符时值"));
        return false;
    }
    *rest = QVariantMap {
        { "time", time.trimmed() },
        { "voice", voice },
        { "duration", duration },
        { "dots", 0 },
        { "review", false },
        { "review_resolution", "manual-review" },
        { "source", "manual-review" },
    };
    return true;
}

QString AiTranscriptionModel::resolvePython() const
{
    const QString override = qEnvironmentVariable("DBSCORE_AI_PYTHON");
    if (!override.isEmpty()) {
        return override;
    }
    const QStringList candidates = {
        applicationResourcePath("ai_transcription/python/bin/python3"),
        applicationResourcePath("python/bin/python3"),
        applicationResourcePath("ai_transcription/python-win/python.exe"),
        applicationResourcePath("ai_transcription/python/python.exe"),
        findInParents("ai_transcription/python-win/python.exe"),
        findInParents("ai_transcription/python/bin/python3"),
        findInParents(".venv-image-to-db/bin/python"),
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
        QStandardPaths::findExecutable("python3"),
        QStandardPaths::findExecutable("python"),
    };
    for (const QString& candidate : candidates) {
        if (!candidate.isEmpty() && QFileInfo(candidate).isExecutable()) {
            return candidate;
        }
    }
    return QString();
}

QString AiTranscriptionModel::resolveEngine() const
{
    const QString override = qEnvironmentVariable("DBSCORE_AI_ENGINE");
    if (!override.isEmpty()) {
        return override;
    }
    const QStringList candidates = {
        applicationResourcePath("ai_transcription/ai_transcribe.py"),
        findInParents("tools/ai_transcription/ai_transcribe.py"),
    };
    for (const QString& candidate : candidates) {
        if (!candidate.isEmpty() && QFileInfo::exists(candidate)) {
            return candidate;
        }
    }
    return QString();
}

QString AiTranscriptionModel::resolveMidiConverter() const
{
    const QString override = qEnvironmentVariable("DBSCORE_MIDI_CONVERTER");
    if (!override.isEmpty()) {
        return override;
    }
#ifdef Q_OS_WIN
    const QString name = "midi-converter.exe";
#else
    const QString name = "midi-converter";
#endif
    const QStringList candidates = {
        applicationResourcePath("plugins/midi_converter/" + name),
        findInParents("build-midi-converter/" + name),
    };
    for (const QString& candidate : candidates) {
        if (!candidate.isEmpty() && QFileInfo(candidate).isExecutable()) {
            return candidate;
        }
    }
    return QString();
}

QString AiTranscriptionModel::resolveStyle() const
{
    const QString override = qEnvironmentVariable("DBSCORE_AI_STYLE");
    if (!override.isEmpty()) {
        return override;
    }
    const QStringList candidates = {
        applicationResourcePath("ai_transcription/drum-style.db"),
        findInParents("share/ai_transcription/drum-style.db"),
    };
    for (const QString& candidate : candidates) {
        if (!candidate.isEmpty() && QFileInfo::exists(candidate)) {
            return candidate;
        }
    }
    return QString();
}

QString AiTranscriptionModel::resolveAudiveris() const
{
    const QString override = qEnvironmentVariable("DBSCORE_AUDIVERIS");
    if (!override.isEmpty()) {
        return override;
    }

    const QString appDir = QCoreApplication::applicationDirPath();
    QStringList candidates;

#ifdef Q_OS_MACOS
    const QString bundledSubdir = QSysInfo::currentCpuArchitecture() == "arm64"
                                  ? "mac-arm64" : "mac-x86_64";
    candidates << QDir(appDir).filePath(
        "../Resources/ai_transcription/audiveris/" + bundledSubdir
        + "/Audiveris.app/Contents/MacOS/Audiveris");
    candidates << findInParents(
        "Resources/ai_transcription/audiveris/" + bundledSubdir
        + "/Audiveris.app/Contents/MacOS/Audiveris");
    const QString fallbackSubdir = bundledSubdir == "mac-arm64"
                                   ? "mac-x86_64" : "mac-arm64";
    candidates << findInParents(
        "Resources/ai_transcription/audiveris/" + fallbackSubdir
        + "/Audiveris.app/Contents/MacOS/Audiveris");
#endif

#ifdef Q_OS_WIN
    const QStringList winBundled = {
        QDir(appDir).filePath("../ai_transcription/audiveris/Audiveris.exe"),
        QDir(appDir).filePath("../ai_transcription/audiveris/bin/Audiveris.exe"),
        findInParents("ai_transcription/audiveris/Audiveris.exe"),
        findInParents("ai_transcription/audiveris/bin/Audiveris.exe"),
    };
    candidates << winBundled;

    const QString programFiles = qEnvironmentVariable("ProgramFiles");
    const QString programFilesX86 = qEnvironmentVariable("ProgramFiles(x86)");
    const QString localAppData = qEnvironmentVariable("LOCALAPPDATA");
    const QStringList winInstallRoots = { programFiles, programFilesX86, localAppData };
    for (const QString& root : winInstallRoots) {
        if (root.isEmpty()) {
            continue;
        }
        candidates << QDir(root).filePath("Audiveris/Audiveris.exe");
        candidates << QDir(root).filePath("Audiveris/bin/Audiveris.exe");
    }
#endif

    candidates << QStringList {
        "/Volumes/Audiveris/Audiveris.app/Contents/MacOS/Audiveris",
        "/Applications/Audiveris.app/Contents/MacOS/Audiveris",
        QStandardPaths::findExecutable("audiveris"),
    };
    for (const QString& candidate : candidates) {
        if (!candidate.isEmpty() && QFileInfo(candidate).isFile()) {
            return candidate;
        }
    }
    return QString();
}

QString AiTranscriptionModel::resolvePdfToPpm() const
{
    const QString override = qEnvironmentVariable("DBSCORE_PDFTOPPM");
    if (!override.isEmpty()) {
        return override;
    }
    return QStandardPaths::findExecutable("pdftoppm");
}

QString AiTranscriptionModel::applicationExecutable() const
{
    const QString override = qEnvironmentVariable("DBSCORE_APPLICATION_PATH");
    return override.isEmpty() ? QCoreApplication::applicationFilePath() : override;
}

QString AiTranscriptionModel::applicationResourcePath(
    const QString& relativePath) const
{
    const QDir executableDir(QCoreApplication::applicationDirPath());
    const QStringList roots = {
        executableDir.filePath("resources"),
        QDir(executableDir.filePath("..")).filePath("Resources"),
    };
    for (const QString& root : roots) {
        const QString candidate = QDir(root).filePath(relativePath);
        if (QFileInfo::exists(candidate)) {
            return candidate;
        }
    }
    return QDir(roots.first()).filePath(relativePath);
}

QString AiTranscriptionModel::pythonHomeFor(const QString& pythonPath) const
{
    if (pythonPath.isEmpty()) {
        return QString();
    }
    const QDir binDir = QFileInfo(pythonPath).absoluteDir();
    if (binDir.dirName() != "bin") {
        return QString();
    }
    const QString root = QDir::cleanPath(
        QDir(binDir.absolutePath()).filePath(".."));
    const QDir rootDir(root);
    if (!QFileInfo(rootDir.filePath("Python3")).isFile()) {
        return QString();
    }
    const QStringList libraries = QDir(rootDir.filePath("lib")).entryList(
        { "python3.*" },
        QDir::Dirs | QDir::NoDotAndDotDot);
    return libraries.isEmpty() ? QString() : root;
}

QString AiTranscriptionModel::findInParents(const QString& relativePath) const
{
    QDir dir(QCoreApplication::applicationDirPath());
    for (int depth = 0; depth < 10; ++depth) {
        const QString candidate = dir.filePath(relativePath);
        if (QFileInfo::exists(candidate)) {
            return candidate;
        }
        if (!dir.cdUp()) {
            break;
        }
    }
    dir = QDir::current();
    for (int depth = 0; depth < 10; ++depth) {
        const QString candidate = dir.filePath(relativePath);
        if (QFileInfo::exists(candidate)) {
            return candidate;
        }
        if (!dir.cdUp()) {
            break;
        }
    }
    return QString();
}

QString AiTranscriptionModel::normalizedBpm(
    const QString& mode,
    const QString& value) const
{
    if (mode == "auto" || mode == "source") {
        return mode;
    }
    bool ok = false;
    const double bpm = value.toDouble(&ok);
    if (!ok || bpm < 30 || bpm > 300) {
        return QString();
    }
    return QString::number(bpm, 'f', 2);
}
