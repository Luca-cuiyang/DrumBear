/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2022 MuseScore Limited and others
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

#include "openprojectscenario.h"

#include <QTimer>

#include "async/async.h"
#include "translation.h"

#include "cloud/cloudtypes.h"
#include "engraving/engravingerrors.h"
#include "engraving/infrastructure/mscio.h"

#include "notation/imasternotation.h"
#include "notation/inotation.h"

#include "inotationproject.h"
#include "projecterrors.h"
#include "types/projecturis.h"

#include "log.h"

using namespace mu::project;
using namespace mu::notation;
using namespace muse;
using muse::async::Promise;

bool OpenProjectScenario::isUrlSupported(const QUrl& url) const
{
    return url.isLocalFile() && isFileSupported(muse::io::path_t(url));
}

bool OpenProjectScenario::isFileSupported(const muse::io::path_t& path) const
{
    const std::string suffix = io::suffix(path);
    return engraving::isMuseScoreFile(suffix) || readers()->reader(suffix);
}

Promise<Ret> OpenProjectScenario::openProject(const muse::rcommand::Params& params)
{
    const QString url = params.at("url").toQString();
    const QString displayNameOverride = params.at("display_name").toQString();

    return openProject(ProjectFile(QUrl(url), displayNameOverride))
           .then<Ret>(this, [](const Ret& ret, auto resolve) {
        if (!ret) {
            LOGE() << ret.toString();
        }
        return resolve(ret);
    });
}

Promise<Ret> OpenProjectScenario::openProject(const ProjectFile& file)
{
    LOGI() << "Try open project: url = " << file.url.toString()
           << ", displayNameOverride = " << file.displayNameOverride;

    if (file.isNull()) {
        return selectScoreOpeningFile().then<Ret>(this, [this](const io::path_t& askedPath, auto resolve) {
            if (askedPath.empty()) {
                return resolve(make_ret(Ret::Code::Cancel));
            }

            configuration()->setLastOpenedProjectsPath(io::dirpath(askedPath));
            openProject(askedPath).onResolve(this, [resolve](const Ret& ret) {
                (void)resolve(ret);
            });
            return Promise<Ret>::dummy_result();
        });
    }

    if (file.url.isLocalFile()) {
        return openProject(file.path(), file.displayNameOverride);
    }

    return resolvedPromise(make_ret(Err::UnsupportedUrl));
}

bool OpenProjectScenario::isBusy(BusyStatus status) const
{
    return m_busyStatuses.contains(status);
}

void OpenProjectScenario::setBusy(BusyStatus status, bool isBusy)
{
    bool wasBusy = m_busyStatuses.contains(status);
    if (wasBusy == isBusy) {
        return;
    }

    if (isBusy) {
        m_busyStatuses.insert(status);
    } else {
        m_busyStatuses.erase(status);
    }

    m_busyChanged.notify();
}

muse::async::Notification OpenProjectScenario::busyChanged() const
{
    return m_busyChanged;
}

Promise<Ret> OpenProjectScenario::runIfNotBusy(BusyStatus status, const std::function<Promise<Ret>()>& flow)
{
    if (isBusy(status)) {
        return resolvedPromise(make_ret(Ret::Code::Busy));
    }

    setBusy(status, true);

    return flow().then<Ret>(this, [this, status](const Ret& ret, auto resolve) {
        setBusy(status, false);
        return resolve(ret);
    });
}

Promise<Ret> OpenProjectScenario::openProject(const muse::io::path_t& givenPath, const QString& displayNameOverride)
{
    return runIfNotBusy(BusyStatus::Opening, [this, givenPath, displayNameOverride]() -> Promise<Ret> {
        //! Step 1. Take absolute path
        muse::io::path_t actualPath = fileSystem()->absoluteFilePath(givenPath);
        if (actualPath.empty()) {
            // We assume that a valid path has been specified to this method
            return resolvedPromise(make_ret(Ret::Code::UnknownError));
        }

        //! Step 2. If the project is already open in the current window, then just switch to showing the notation
        if (isProjectOpened(actualPath)) {
            return resolvedPromise(finishOpening());
        }

        //! Step 3. Check, if the project already opened in another window, then activate the window with the project
        if (multiwindowsProvider()->isProjectAlreadyOpened(actualPath)) {
            multiwindowsProvider()->activateWindowWithProject(actualPath);
            return resolvedPromise(make_ok());
        }

        //! Step 4. Check, if a any project is already open in the current window,
        //! then create a new instance
        if (globalContext()->currentProject()) {
            QStringList args;
            args << actualPath.toQString();

            if (!displayNameOverride.isEmpty()) {
                args << "--score-display-name-override" << displayNameOverride;
            }

            multiwindowsProvider()->openNewWindow(args);
            return resolvedPromise(make_ok());
        }

        //! Step 5. Legacy cloud projects are opened from their local cached file only.
        if (configuration()->isCloudProject(actualPath) && !configuration()->isLegacyCloudProject(actualPath)) {
            if (!fileSystem()->exists(actualPath)) {
                return resolvedPromise(make_ret(
                    Ret::Code::NotSupported,
                    std::string("旧云端曲谱同步已停用，本地副本不存在。")));
            }
            return doOpenCloudProjectOffline(actualPath, displayNameOverride);
        }

        //! Step 6. Open project in the current window
        return doOpenProject(actualPath);
    });
}

Promise<RetVal<INotationProjectPtr> > OpenProjectScenario::loadProject(const muse::io::path_t& filePath)
{
    TRACEFUNC;

    const auto project = projectCreator()->newProject(iocContext());
    IF_ASSERT_FAILED(project) {
        return resolvedPromise(RetVal<INotationProjectPtr>(make_ret(Ret::Code::InternalError)));
    }

    const bool hasUnsavedChanges = projectAutoSaver()->projectHasUnsavedChanges(filePath);

    const muse::io::path_t loadPath = hasUnsavedChanges ? projectAutoSaver()->projectAutoSavePath(filePath) : filePath;
    const std::string format = io::suffix(filePath);

    return loadWithFallback(project, loadPath, format)
           .then<RetVal<INotationProjectPtr> >(this, [this, project, filePath, hasUnsavedChanges](const Ret& result, auto resolve) {
        if (!result) {
            return resolve(RetVal<INotationProjectPtr>(result));
        }

        if (hasUnsavedChanges) {
            //! NOTE: redirect the project to the original file path
            project->setPath(filePath);

            project->markAsUnsaved();
        }

        if (projectAutoSaver()->isAutosaveOfNewlyCreatedProject(filePath)) {
            project->markAsNewlyCreated();
        }

        return resolve(RetVal<INotationProjectPtr>::make_ok(project));
    });
}

Promise<Ret> OpenProjectScenario::loadWithFallback(const std::shared_ptr<INotationProject>& project,
                                                   const muse::io::path_t& loadPath,
                                                   const std::string& format)
{
    Ret result = project->load(loadPath, OpenParams(), format);

    if (result || result.code() == static_cast<int>(Ret::Code::Cancel)) {
        return resolvedPromise(result);
    }

    return shouldRetryLoadAfterError(result, loadPath)
           .then<Ret>(this, [project, loadPath, format, result](bool forceLoad, auto resolve) {
        if (!forceLoad) {
            return resolve(result);
        }

        OpenParams params;
        params.forceMode = forceLoad;
        return resolve(project->load(loadPath, params, format));
    });
}

Promise<Ret> OpenProjectScenario::doOpenProject(const muse::io::path_t& filePath)
{
    TRACEFUNC;

    return loadProject(filePath).then<Ret>(this, [this, filePath](const RetVal<INotationProjectPtr>& rv, auto resolve) {
        if (!rv.ret) {
            return resolve(rv.ret);
        }

        INotationProjectPtr project = rv.val;

        bool isNewlyCreated = projectAutoSaver()->isAutosaveOfNewlyCreatedProject(filePath);
        if (!isNewlyCreated) {
            recentFilesController()->prependRecentFile(makeRecentFile(project));
        }

        globalContext()->setCurrentProject(project);

        return resolve(finishOpening());
    });
}

Promise<Ret> OpenProjectScenario::doOpenCloudProjectOffline(const muse::io::path_t& filePath, const QString& displayNameOverride)
{
    return loadProject(filePath)
           .then<Ret>(this, [this, displayNameOverride](const RetVal<INotationProjectPtr>& rv, auto resolve) {
        if (!rv.ret) {
            return resolve(rv.ret);
        }

        INotationProjectPtr project = rv.val;
        CloudProjectInfo info = project->cloudInfo();
        info.name = displayNameOverride;
        project->setCloudInfo(info);

        recentFilesController()->prependRecentFile(makeRecentFile(project));
        globalContext()->setCurrentProject(project);

        return resolve(finishOpening());
    });
}

Ret OpenProjectScenario::finishOpening()
{
    const Uri pageUri = resolveNotationPageUri();

    //! Show MuseSounds / MuseSampler update if need
    auto showUpdateNotification = [this]() {
        QTimer::singleShot(1000, [this]() {
            if (museSoundsCheckUpdateScenario()->hasUpdate()) {
                museSoundsCheckUpdateScenario()->showUpdate();
            } else if (!museSamplerCheckUpdateScenario()->alreadyChecked()) {
                museSamplerCheckUpdateScenario()->checkAndShowUpdateIfNeed();
            }
        });
    };

    if (pageUri == NOTATION_PAGE_URI) {
        if (interactive()->isOpened(NOTATION_PAGE_URI).val) {
            showUpdateNotification();
        } else {
            async::Channel<Uri> opened = interactive()->opened();
            opened.onReceive(this, [this, opened, showUpdateNotification](const Uri&) {
                async::Async::call(this, [this, opened, showUpdateNotification]() {
                    async::Channel<Uri> mut = opened;
                    mut.disconnect(this);

                    showUpdateNotification();
                });
            });
        }
    }

    return openPageIfNeed(pageUri);
}

Uri OpenProjectScenario::resolveNotationPageUri() const
{
    return NOTATION_PAGE_URI;
}

const ProjectBeingDownloaded& OpenProjectScenario::projectBeingDownloaded() const
{
    return m_projectBeingDownloaded;
}

muse::async::Notification OpenProjectScenario::projectBeingDownloadedChanged() const
{
    return m_projectBeingDownloadedChanged;
}

Ret OpenProjectScenario::openPageIfNeed(Uri pageUri)
{
    if (!interactive()->isOpened(pageUri).val) {
        interactive()->open(pageUri);
    }
    return make_ret(Ret::Code::Ok);
}

bool OpenProjectScenario::isProjectOpened(const muse::io::path_t& scorePath) const
{
    auto project = globalContext()->currentProject();
    if (!project) {
        return false;
    }

    LOGD() << "project->path: " << project->path() << ", check path: " << scorePath;
    if (project->path() == scorePath) {
        return true;
    }

    return false;
}

RecentFile OpenProjectScenario::makeRecentFile(INotationProjectPtr project)
{
    RecentFile file;
    file.path = project->path();

    if (project->isCloudProject()) {
        file.displayNameOverride = project->cloudInfo().name;
    }

    return file;
}

Promise<Ret> OpenProjectScenario::revertToLastSaved()
{
    TRACEFUNC;

    auto currentProject = globalContext()->currentProject();
    if (!currentProject) {
        return resolvedPromise(make_ret(Err::NoProjectError));
    }

    muse::io::path_t filePath = currentProject->path();

    bool hasUnsavedChanges = projectAutoSaver()->projectHasUnsavedChanges(filePath);
    if (hasUnsavedChanges) {
        muse::io::path_t autoSavePath = projectAutoSaver()->projectAutoSavePath(filePath);
        fileSystem()->remove(autoSavePath);
    }

    return runIfNotBusy(BusyStatus::Opening, [this, filePath]() {
        return doOpenProject(filePath);
    });
}

Promise<bool> OpenProjectScenario::shouldRetryLoadAfterError(const Ret& ret, const muse::io::path_t& filepath)
{
    if (ret) {
        return resolvedPromise(true);
    }

    switch (static_cast<engraving::Err>(ret.code())) {
    case engraving::Err::FileTooOld:
    case engraving::Err::FileOld300Format:
        return askIfUserAgreesToOpenProjectWithIncompatibleVersion(ret.text());
    case engraving::Err::FileTooNew:
        warnFileTooNew(filepath);
        return resolvedPromise(configuration()->disableVersionChecking());
    case engraving::Err::FileCorrupted:
        return askIfUserAgreesToOpenCorruptedProject(io::filename(filepath).toString(), ret.text());
    case engraving::Err::FileCriticallyCorrupted:
        warnProjectCriticallyCorrupted(io::filename(filepath).toString(), ret.text());
        return resolvedPromise(false);
    default:
        warnProjectCannotBeOpened(ret, filepath);
        break;
    }

    return resolvedPromise(false);
}

Promise<bool> OpenProjectScenario::askIfUserAgreesToOpenProjectWithIncompatibleVersion(const std::string& errorText)
{
    IInteractive::ButtonData openAnywayBtn(IInteractive::Button::CustomButton, muse::trc("project", "Open anyway"), true /*accent*/);

    return interactive()->warning(errorText, IInteractive::Text(), {
        interactive()->buttonData(IInteractive::Button::Cancel),
        openAnywayBtn
    }, openAnywayBtn.btn)
           .then<bool>(this, [openAnywayBtn](const IInteractive::Result& res, auto resolve) {
        return resolve(res.isButton(openAnywayBtn.btn));
    });
}

void OpenProjectScenario::warnFileTooNew(const muse::io::path_t& filepath)
{
    interactive()->error(muse::qtrc("project", "Cannot read file %1").arg(io::toNativeSeparators(filepath).toQString()).toStdString(),
                         muse::mtrc("project", "This file was saved using a newer version of MuseScore Studio. "
                                               "Please visit <a href=\"%1\">drumbear.cn</a> to obtain the latest version.")
                         .arg(u"https://drumbear.cn").toStdString());
}

Promise<bool> OpenProjectScenario::askIfUserAgreesToOpenCorruptedProject(const String& projectName, const std::string& errorText)
{
    std::string title = muse::mtrc("project", "File “%1” is corrupted").arg(projectName).toStdString();
    IInteractive::Text text;
    text.text = muse::trc("project", "This file contains errors that could cause MuseScore Studio to malfunction.");
    text.detailedText = errorText;

    IInteractive::ButtonData openAnywayBtn(IInteractive::Button::CustomButton, muse::trc("project", "Open anyway"), true /*accent*/);

    return interactive()->warning(title, text, {
        interactive()->buttonData(IInteractive::Button::Cancel),
        openAnywayBtn
    }, openAnywayBtn.btn)
           .then<bool>(this, [openAnywayBtn](const IInteractive::Result& res, auto resolve) {
        return resolve(res.isButton(openAnywayBtn.btn));
    });
}

void OpenProjectScenario::warnProjectCriticallyCorrupted(const String& projectName, const std::string& errorText)
{
    std::string title = muse::mtrc("project", "File “%1” is corrupted and cannot be opened").arg(projectName).toStdString();
    IInteractive::Text text;
    text.text = muse::trc("project", "Get help for this issue on drumbear.cn.");
    text.detailedText = errorText;

    IInteractive::ButtonData getHelpBtn(IInteractive::Button::CustomButton, muse::trc("project", "Get help"), true /*accent*/);

    interactive()->error(title, text, {
        interactive()->buttonData(IInteractive::Button::Cancel),
        getHelpBtn
    }, getHelpBtn.btn).onResolve(this, [this, getHelpBtn](const IInteractive::Result& res) {
        if (res.isButton(getHelpBtn.btn)) {
            platformInteractive()->openUrl(configuration()->supportForumUrl());
        }
    });
}

void OpenProjectScenario::warnProjectCannotBeOpened(const Ret& ret, const muse::io::path_t& filepath)
{
    std::string title = muse::mtrc("project", "Cannot read file %1").arg(io::toNativeSeparators(filepath).toString()).toStdString();
    std::string body;

    switch (ret.code()) {
    case int(engraving::Err::FileNotFound):
        body = muse::trc("project", "This file does not exist or cannot be accessed at the moment.");
        break;
    case int(engraving::Err::FileOpenError):
        body = muse::trc("project",
                         "This file could not be opened. Please make sure that MuseScore Studio has permission to read this file.");
        break;
    default:
        if (!ret.text().empty()) {
            body = ret.text();
        } else {
            body = muse::trc("project", "An error occurred while reading this file.");
        }
    }

    interactive()->error(title, body);
}

async::Promise<io::path_t> OpenProjectScenario::selectScoreOpeningFile() const
{
    std::string allExt = "*.db *.mscz *.mxl *.musicxml *.xml *.mid *.midi *.kar *.md *.mgu *.sgu *.cap *.capx "
                         "*.ove *.scw *.bmw *.bww *.gtp *.gp3 *.gp4 *.gp5 *.gpx *.gp *.ptb *.mei *.mnx *.json *.tef *.mscx *.mscs *.db~ *.mscz~";

    std::vector<std::string> filter { muse::trc("project", "All supported files") + " (" + allExt + ")",
                                      muse::trc("project", "DB Score 文件") + " (*.db *.mscz)",
                                      muse::trc("project", "MusicXML files") + " (*.mxl *.musicxml *.xml)",
                                      muse::trc("project", "MIDI files") + " (*.mid *.midi *.kar)",
                                      muse::trc("project", "MNX files [experimental]") + " (*.mnx *.json)",
                                      muse::trc("project", "MuseData files") + " (*.md)",
                                      muse::trc("project", "Capella files") + " (*.cap *.capx)",
                                      muse::trc("project", "BB files [experimental]") + " (*.mgu *.sgu)",
                                      muse::trc("project", "Overture / Score Writer files [experimental]") + " (*.ove *.scw)",
                                      muse::trc("project", "Bagpipe Music Writer files [experimental]") + " (*.bmw *.bww)",
                                      muse::trc("project", "Guitar Pro files") + " (*.gtp *.gp3 *.gp4 *.gp5 *.gpx *.gp)",
                                      muse::trc("project", "Power Tab Editor files [experimental]") + " (*.ptb)",
                                      muse::trc("project", "MEI files") + " (*.mei)",
                                      muse::trc("project", "TablEdit files [experimental]") + " (*.tef)",
                                      muse::trc("project", "Uncompressed MuseScore folders [experimental]") + " (*.mscx)",
                                      muse::trc("project", "MuseScore developer files") + " (*.mscs)",
                                      muse::trc("project", "DB Score 备份文件") + " (*.db~ *.mscz~)" };

    muse::io::path_t defaultDir = configuration()->lastOpenedProjectsPath();

    if (defaultDir.empty()) {
        defaultDir = configuration()->userProjectsPath();
    }

    if (defaultDir.empty()) {
        defaultDir = configuration()->defaultUserProjectsPath();
    }

    return interactive()->selectOpeningFile(muse::trc("project", "Open"), defaultDir, filter);
}
