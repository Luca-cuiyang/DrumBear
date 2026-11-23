/*
 * SPDX-License-Identifier: GPL-3.0-only
 */

#pragma once

#include <memory>

#include <QObject>
#include <QProcess>
#include <QQmlEngine>
#include <QStringList>
#include <QTemporaryDir>
#include <QTimer>
#include <QVariantList>
#include <QVariantMap>

#include "actions/iactionsdispatcher.h"
#include "modularity/ioc.h"

namespace mu::appshell {
class AiTranscriptionModel : public QObject, public muse::Contextable
{
    Q_OBJECT

    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(bool completed READ completed NOTIFY completedChanged)
    Q_PROPERTY(QString statusText READ statusText NOTIFY statusTextChanged)
    Q_PROPERTY(QString logText READ logText NOTIFY logTextChanged)
    Q_PROPERTY(QString inputSummary READ inputSummary NOTIFY inputSummaryChanged)
    Q_PROPERTY(QString outputPath READ outputPath NOTIFY outputPathChanged)
    Q_PROPERTY(QString sourceKind READ sourceKind NOTIFY sourceKindChanged)
    Q_PROPERTY(QVariantMap report READ report NOTIFY reportChanged)
    Q_PROPERTY(bool reviewRequired READ reviewRequired NOTIFY reviewStateChanged)
    Q_PROPERTY(QString reviewProjectPath READ reviewProjectPath NOTIFY reviewStateChanged)
    Q_PROPERTY(QVariantList reviewMeasures READ reviewMeasures NOTIFY reviewStateChanged)
    Q_PROPERTY(QVariantList reviewPages READ reviewPages NOTIFY reviewStateChanged)
    Q_PROPERTY(int reviewedMeasureCount READ reviewedMeasureCount NOTIFY reviewStateChanged)
    Q_PROPERTY(int reviewMeasureCount READ reviewMeasureCount NOTIFY reviewStateChanged)
    Q_PROPERTY(int selectedReviewMeasure READ selectedReviewMeasure NOTIFY reviewStateChanged)
    Q_PROPERTY(int selectedReviewMeasureLength READ selectedReviewMeasureLength NOTIFY reviewStateChanged)
    Q_PROPERTY(QVariantList selectedReviewEvents READ selectedReviewEvents NOTIFY reviewStateChanged)
    Q_PROPERTY(QVariantList selectedReviewRests READ selectedReviewRests NOTIFY reviewStateChanged)
    Q_PROPERTY(QVariantList selectedReviewVisualErrors READ selectedReviewVisualErrors NOTIFY reviewStateChanged)
    Q_PROPERTY(QString selectedReviewSourceCrop READ selectedReviewSourceCrop NOTIFY reviewStateChanged)

    QML_ELEMENT

    muse::ContextInject<muse::actions::IActionsDispatcher> dispatcher = { this };

public:
    explicit AiTranscriptionModel(QObject* parent = nullptr);
    ~AiTranscriptionModel() override;

    bool busy() const;
    bool completed() const;
    QString statusText() const;
    QString logText() const;
    QString inputSummary() const;
    QString outputPath() const;
    QString sourceKind() const;
    QVariantMap report() const;
    bool reviewRequired() const;
    QString reviewProjectPath() const;
    QVariantList reviewMeasures() const;
    QVariantList reviewPages() const;
    int reviewedMeasureCount() const;
    int reviewMeasureCount() const;
    int selectedReviewMeasure() const;
    int selectedReviewMeasureLength() const;
    QVariantList selectedReviewEvents() const;
    QVariantList selectedReviewRests() const;
    QVariantList selectedReviewVisualErrors() const;
    QString selectedReviewSourceCrop() const;

    Q_INVOKABLE bool startMidi(
        const QString& inputPath,
        const QString& outputPath,
        const QString& grid,
        const QString& bpmMode,
        const QString& bpmValue,
        const QString& startShift,
        int leadingMeasures);
    Q_INVOKABLE bool startImages(
        const QVariantList& inputPaths,
        const QString& outputPath,
        const QString& title,
        int tempo);
    Q_INVOKABLE bool setMeasureReviewed(int number, bool reviewed);
    Q_INVOKABLE bool markAllMeasuresReviewed();
    Q_INVOKABLE void selectReviewMeasure(int number);
    Q_INVOKABLE bool updateReviewEvent(
        int measureNumber,
        int eventIndex,
        const QString& time,
        const QString& pitches);
    Q_INVOKABLE bool addReviewEvent(
        int measureNumber,
        const QString& time,
        const QString& pitches);
    Q_INVOKABLE bool deleteReviewEvent(int measureNumber, int eventIndex);
    Q_INVOKABLE bool updateReviewRest(
        int measureNumber,
        int restIndex,
        const QString& time,
        const QString& voice,
        const QString& duration);
    Q_INVOKABLE bool addReviewRest(
        int measureNumber,
        const QString& time,
        const QString& voice,
        const QString& duration);
    Q_INVOKABLE bool deleteReviewRest(int measureNumber, int restIndex);
    Q_INVOKABLE bool reflowReviewMeasure(int measureNumber);
    Q_INVOKABLE bool updateReviewMeasureLength(int measureNumber, int beats);
    Q_INVOKABLE bool finalizeImageReview();
    Q_INVOKABLE bool loadReviewProject(const QString& projectPath);
    Q_INVOKABLE void revealReviewProject();
    Q_INVOKABLE void cancel();
    Q_INVOKABLE void reset();
    Q_INVOKABLE void showError(const QString& message);
    Q_INVOKABLE bool openOutputInScore();
    Q_INVOKABLE void revealOutput();
    Q_INVOKABLE QString environmentDiagnostics() const;

signals:
    void busyChanged();
    void completedChanged();
    void statusTextChanged();
    void logTextChanged();
    void inputSummaryChanged();
    void outputPathChanged();
    void sourceKindChanged();
    void reportChanged();
    void reviewStateChanged();

private:
    void startJob(const QStringList& arguments, const QString& kind);
    void readProcessOutput();
    void finishJob(int exitCode, QProcess::ExitStatus exitStatus);
    void setBusy(bool value);
    void setCompleted(bool value);
    void setStatusText(const QString& value);
    void appendLog(const QString& value);
    void setInputSummary(const QString& value);
    void setOutputPath(const QString& value);
    void setSourceKind(const QString& value);
    void setReport(const QVariantMap& value);
    void clearReviewState();
    bool loadReview(const QVariantMap& report);
    bool saveReview();
    bool applyReviewEvents(int measureNumber, const QVariantList& events);
    bool applyReviewRests(int measureNumber, const QVariantList& rests);
    QVariantMap buildReviewEvent(const QString& time, const QStringList& pitches) const;
    bool parseReviewEvent(
        const QString& time,
        const QString& pitches,
        int measureLength,
        QVariantMap* event);
    bool parseReviewRest(
        const QString& time,
        const QString& voice,
        const QString& duration,
        int measureLength,
        QVariantMap* rest);

    QString resolvePython() const;
    QString resolveEngine() const;
    QString resolveMidiConverter() const;
    QString resolveStyle() const;
    QString resolveAudiveris() const;
    QString resolvePdfToPpm() const;
    QString applicationExecutable() const;
    QString applicationResourcePath(const QString& relativePath) const;
    QString pythonHomeFor(const QString& pythonPath) const;
    QString findInParents(const QString& relativePath) const;
    QString normalizedBpm(const QString& mode, const QString& value) const;

    QProcess m_process;
    QTimer m_jobTimeoutTimer;
    std::unique_ptr<QTemporaryDir> m_jobDir;
    QString m_reportPath;
    QString m_statusBuffer;
    int m_processGeneration = 0;
    bool m_busy = false;
    bool m_completed = false;
    bool m_cancelRequested = false;
    bool m_timeoutRequested = false;
    QString m_statusText;
    QString m_logText;
    QString m_inputSummary;
    QString m_outputPath;
    QString m_sourceKind;
    QVariantMap m_report;
    bool m_reviewRequired = false;
    QString m_reviewProjectPath;
    QString m_reviewPath;
    QVariantMap m_reviewData;
    QVariantList m_reviewMeasures;
    QVariantList m_reviewPages;
    QVariantList m_selectedReviewEvents;
    QVariantList m_selectedReviewRests;
    QVariantList m_selectedReviewVisualErrors;
    QString m_selectedReviewSourceCrop;
    int m_reviewedMeasureCount = 0;
    int m_reviewMeasureCount = 0;
    int m_selectedReviewMeasure = 0;
    int m_selectedReviewMeasureLength = 4;
};
}
