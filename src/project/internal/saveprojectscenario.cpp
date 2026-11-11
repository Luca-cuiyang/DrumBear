/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2026 MuseScore Limited and others
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

#include "saveprojectscenario.h"

#include <QFileInfo>

#include "translation.h"

#include "engraving/infrastructure/mscio.h"

#include "notation/imasternotation.h"
#include "notation/inotation.h"
#include "notation/inotationinteraction.h"

#include "inotationproject.h"
#include "projecterrors.h"
#include "types/projecturis.h"

#include "log.h"

using namespace mu::project;
using namespace mu::notation;
using namespace muse;
using muse::async::Promise;

template<typename T>
static Promise<T> resolvedPromise(const T& value)
{
    return async::make_promise<T>([value](auto resolve) {
        return resolve(value);
    });
}

static constexpr int RETRY_SAVE_BTN_ID = int(IInteractive::Button::CustomButton);
static constexpr int SAVE_AS_BTN_ID    = RETRY_SAVE_BTN_ID + 1;

INotationProjectPtr SaveProjectScenario::currentNotationProject() const
{
    return globalContext()->currentProject();
}

INotationInteractionPtr SaveProjectScenario::currentInteraction() const
{
    INotationProjectPtr project = currentNotationProject();
    if (!project || !project->masterNotation() || !project->masterNotation()->notation()) {
        return nullptr;
    }

    return project->masterNotation()->notation()->interaction();
}

bool SaveProjectScenario::ensureCanSaveProFeatures(const INotationProjectPtr& project)
{
    if (!project || !project->audioSettings()) {
        return true;
    }

    bool hasAudioTrack = project->audioSettings()->audioTrackSettings().isValid();
    if (!hasAudioTrack) {
        return true;
    }

    if (authorization() && authorization()->hasProAccess()) {
        return true;
    }

    auto result = interactive()->questionSync(
        muse::trc("project", "会员功能"),
        muse::trc("project", "保存带音频的动态.dbscore工程是会员专属功能。\n请激活会员后使用（含3天免费试用）。"),
        { muse::IInteractive::Button::Ok, muse::IInteractive::Button::Cancel },
        muse::IInteractive::Button::Ok);

    if (result.standardButton() == muse::IInteractive::Button::Ok) {
        interactive()->open("dbscore://account");
    }

    return false;
}

bool SaveProjectScenario::isBusy(BusyStatus status) const
{
    return m_busyStatuses.contains(status);
}

void SaveProjectScenario::setBusy(BusyStatus status, bool isBusy)
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

muse::async::Notification SaveProjectScenario::busyChanged() const
{
    return m_busyChanged;
}

Promise<Ret> SaveProjectScenario::runIfNotBusy(BusyStatus status, const std::function<Promise<Ret>()>& flow)
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

Ret SaveProjectScenario::canSaveProject() const
{
    auto project = currentNotationProject();
    if (!project) {
        LOGW() << "no current project";
        return make_ret(Err::NoProjectError);
    }

    return project->canSave();
}

Promise<Ret> SaveProjectScenario::saveProject(const muse::io::path_t& path)
{
    if (path.empty()) {
        return saveProject(SaveMode::Save);
    }

    return runIfNotBusy(BusyStatus::Saving, [this, path]() {
        return saveProjectAt(SaveLocation(SaveLocationType::Local, path));
    });
}

Promise<Ret> SaveProjectScenario::saveProject(SaveMode saveMode, SaveLocationType saveLocationType, bool force)
{
    (void)saveLocationType;
    return runIfNotBusy(BusyStatus::Saving, [this, saveMode, force]() -> Promise<Ret> {
        INotationProjectPtr project = currentNotationProject();
        if (!project) {
            LOGW() << "no current project";
            return resolvedPromise(make_ret(Err::NoProjectError));
        }

        const bool isExistingSave = saveMode == SaveMode::Save && !project->isNewlyCreated();
        if (isExistingSave) {
            // 默认直接保存到本地
            return saveProjectAt(SaveLocation(SaveLocationType::Local), saveMode, force);
        }

        // 新文件：直接本地文件选择器，不再弹“本地/云端”选择
        return askSaveLocation(project, saveMode, SaveLocationType::Local)
               .then<Ret>(this, [this, saveMode, force](const RetVal<SaveLocation>& response, auto resolve) {
            if (!response.ret) {
                LOGE() << response.ret.toString();
                return resolve(response.ret);
            }

            saveProjectAt(response.val, saveMode, force).onResolve(this, [resolve](const Ret& ret) {
                (void)resolve(ret);
            });

            return Promise<Ret>::dummy_result();
        });
    });
}

Promise<Ret> SaveProjectScenario::publish()
{
    return resolvedPromise(make_ret(
        Ret::Code::NotSupported,
        std::string("发布功能未启用，请将文件保存到本地后上传到 DB后台端。")));
}

Promise<Ret> SaveProjectScenario::shareAudio()
{
    return resolvedPromise(make_ret(
        Ret::Code::NotSupported,
        std::string("音频分享功能未启用。")));
}

Promise<Ret> SaveProjectScenario::saveProjectAt(const muse::rcommand::Params& params)
{
    const std::string& path = params.at("path").toString();
    if (path.empty()) {
        return resolvedPromise(make_ret(Ret::Code::BadArgs));
    }

    return runIfNotBusy(BusyStatus::Saving, [this, path]() {
        return saveProjectAt(SaveLocation(muse::io::path_t(path)));
    });
}

Promise<Ret> SaveProjectScenario::saveProjectAt(const SaveLocation& location, SaveMode saveMode, bool force)
{
    INotationInteractionPtr interaction = currentInteraction();
    if (interaction && interaction->isTextEditingStarted()) {
        interaction->endEditText();
    }

    if (!force) {
        Ret ret = canSaveProject();
        if (!ret) {
            return askIfUserAgreesToSaveProjectWithErrors(ret, location)
                   .then<Ret>(this, [this, location, saveMode, ret](bool agreed, auto resolve) {
                if (!agreed) {
                    return resolve(ret);
                }

                doSaveProjectAt(location, saveMode).onResolve(this, [resolve](const Ret& saveRet) {
                    (void)resolve(saveRet);
                });

                return Promise<Ret>::dummy_result();
            });
        }
    }

    return doSaveProjectAt(location, saveMode);
}

Promise<Ret> SaveProjectScenario::doSaveProjectAt(const SaveLocation& location, SaveMode saveMode)
{
    if (location.isLocal()) {
        return saveProjectLocally(location.localPath(), saveMode);
    }

    return resolvedPromise(make_ret(Ret::Code::NotSupported));
}

Promise<Ret> SaveProjectScenario::saveProjectLocally(const muse::io::path_t& filePath, SaveMode saveMode, bool createBackup)
{
    INotationProjectPtr project = currentNotationProject();
    if (!project) {
        return resolvedPromise(make_ret(Err::NoProjectError));
    }

    if (!ensureCanSaveProFeatures(project)) {
        return resolvedPromise(make_ret(Ret::Code::Cancel));
    }

    Ret ret = project->save(filePath, saveMode, createBackup);

    if (ret) {
        recentFilesController()->prependRecentFile(makeRecentFile(project));
        return resolvedPromise(make_ok());
    }

    LOGE() << ret.toString();

    if (ret.code() != (int)Err::CorruptionUponSavingError) {
        return warnScoreCouldnotBeSaved(ret);
    }

    return warnScoreHasBecomeCorruptedAfterSave(ret).then<Ret>(this, [this, filePath, saveMode, ret](int btn, auto resolve) {
        switch (btn) {
            case RETRY_SAVE_BTN_ID: {
                // Retry the save. Do not create a backup this time because the target file has been corrupted
                // already. Creating a backup file of a corrupted file now makes no sense and will corrupt
                // the healthy backup file created on the first save attempt.
                saveProjectLocally(filePath, saveMode, false /*createBackup*/).onResolve(this, [resolve](const Ret& retryRet) {
                    (void)resolve(retryRet);
                });

                return Promise<Ret>::dummy_result();
            }

            case SAVE_AS_BTN_ID: {
                //! NOTE The save that started this one still holds the status; the new flow takes it over
                setBusy(BusyStatus::Saving, false);

                saveProject(SaveMode::SaveAs).onResolve(this, [resolve](const Ret& saveAsRet) {
                    (void)resolve(saveAsRet);
                });

                return Promise<Ret>::dummy_result();
            }
        }

        return resolve(ret);
    });
}


Promise<bool> SaveProjectScenario::refuseSaveAfter(Promise<Ret> shown)
{
    return shown.then<bool>(this, [](const Ret&, auto resolve) {
        return resolve(false);
    });
}

Promise<bool> SaveProjectScenario::askIfUserAgreesToSaveProjectWithErrors(const Ret& ret, const SaveLocation& location)
{
    switch (static_cast<Err>(ret.code())) {
    case Err::NoPartsError:
        return refuseSaveAfter(warnScoreCouldnotBeSaved(muse::trc("project/save", "Please add at least one instrument to enable saving.")));
    case Err::CorruptionUponOpenningError:
        return askIfUserAgreesToSaveCorruptedScoreUponOpenning(location, ret.text());
    case Err::CorruptionError: {
        auto project = currentNotationProject();
        return askIfUserAgreesToSaveCorruptedScore(location, ret.text(), project->isNewlyCreated());
    }
    default:
        return resolvedPromise(false);
    }
}

Promise<bool> SaveProjectScenario::askIfUserAgreesToSaveCorruptedScore(const SaveLocation& location, const std::string& errorText,
                                                                       bool newlyCreated)
{
    if (location.isLocal()) {
        return askIfUserAgreesToSaveCorruptedScoreLocally(errorText, !newlyCreated);
    }

    return refuseSaveAfter(showErrCorruptedScoreCannotBeSaved(location, errorText));
}

Promise<bool> SaveProjectScenario::askIfUserAgreesToSaveCorruptedScoreLocally(const std::string& errorText,
                                                                              bool canRevert)
{
    std::string title = muse::trc("project", "This score has become corrupted and contains errors");

    IInteractive::Text text;
    text.text = !canRevert
                ? muse::trc("project", "You can continue saving it locally, although the file may become unusable. "
                                       "You can try to fix the errors manually, or get help for this issue on drumbear.cn.")
                : muse::trc("project", "You can continue saving it locally, although the file may become unusable. "
                                       "To preserve your score, revert to the last saved version, or fix the errors manually. "
                                       "You can also get help for this issue on drumbear.cn.");
    text.detailedText = errorText;

    IInteractive::ButtonDatas buttons;
    buttons.push_back(interactive()->buttonData(IInteractive::Button::Cancel));

    IInteractive::ButtonData saveAnywayBtn(IInteractive::Button::CustomButton, muse::trc("project", "Save anyway"),
                                           !canRevert /*accent*/);
    buttons.push_back(saveAnywayBtn);

    int defaultBtn = saveAnywayBtn.btn;

    IInteractive::ButtonData revertToLastSavedBtn(saveAnywayBtn.btn + 1, muse::trc("project", "Revert to last saved"),
                                                  true /*accent*/);
    if (canRevert) {
        buttons.push_back(revertToLastSavedBtn);
        defaultBtn = revertToLastSavedBtn.btn;
    }

    return interactive()->error(title, text, buttons, defaultBtn)
           .then<bool>(this, [this, saveAnywayBtn, revertToLastSavedBtn](const IInteractive::Result& res, auto resolve) {
        if (res.isButton(revertToLastSavedBtn.btn)) {
            askToRevertCorruptedScoreToLastSaved().onResolve(this, [resolve](const Ret&) {
                (void)resolve(false);
            });

            return Promise<bool>::dummy_result();
        }

        return resolve(res.isButton(saveAnywayBtn.btn));
    });
}

Promise<bool> SaveProjectScenario::askIfUserAgreesToSaveCorruptedScoreUponOpenning(const SaveLocation& location,
                                                                                   const std::string& errorText)
{
    if (location.isLocal()) {
        return askIfUserAgreesToSaveCorruptedScoreLocally(errorText, false /*canRevert*/);
    }

    return refuseSaveAfter(showErrCorruptedScoreCannotBeSaved(location, errorText));
}

Promise<Ret> SaveProjectScenario::showErrCorruptedScoreCannotBeSaved(const SaveLocation& location, const std::string& errorText)
{
    std::string title = location.isLocal()
                        ? muse::trc("project", "Your score cannot be saved")
                        : muse::trc("project", "Your score cannot be uploaded to the cloud");

    IInteractive::Text text;
    text.text = muse::trc("project", "This score is corrupted. You can get help for this issue on drumbear.cn.");
    text.detailedText = errorText;

    IInteractive::ButtonData getHelpBtn(IInteractive::Button::CustomButton, muse::trc("project", "Get help"));

    return interactive()->error(title, text, {
        getHelpBtn,
        interactive()->buttonData(IInteractive::Button::Ok)
    }).then<Ret>(this, [this, getHelpBtn](const IInteractive::Result& res, auto resolve) {
        if (res.isButton(getHelpBtn.btn)) {
            platformInteractive()->openUrl(configuration()->supportForumUrl());
        }

        return resolve(make_ok());
    });
}

Promise<Ret> SaveProjectScenario::warnScoreCouldnotBeSaved(const Ret& ret)
{
    std::string message = ret.text();
    if (message.empty()) {
        message = muse::trc("project/save", "An unknown error occurred while saving this file.");
    }

    return warnScoreCouldnotBeSaved(message)
           .then<Ret>(this, [ret](const Ret&, auto resolve) {
        return resolve(ret);
    });
}

Promise<Ret> SaveProjectScenario::warnScoreCouldnotBeSaved(const std::string& errorText)
{
    return interactive()->warning(muse::trc("project/save", "Your score could not be saved"), errorText)
           .then<Ret>(this, [](const IInteractive::Result&, auto resolve) {
        return resolve(make_ok());
    });
}

Promise<int> SaveProjectScenario::warnScoreHasBecomeCorruptedAfterSave(const Ret& ret)
{
    const QString errDetailsMessage = QString::fromStdString(ret.toString()).toHtmlEscaped();

    const QString supportForumLink = String("<a href=\"%1\" style=\"text-decoration: none\">drumbear.cn</a>")
                                     .arg(configuration()->supportForumUrl().toString());

    const std::string title = muse::trc("project/save", "An error occurred while saving your score");

    const std::string body = muse::qtrc("project/save",
                                        "To preserve your score, try saving it again. "
                                        "If this message still appears, please save your score as new copy. "
                                        "You can also get help for this issue on %1.<br/><br/>"
                                        "Error details (please cite when asking for support): %2")
                             .arg(supportForumLink, errDetailsMessage)
                             .toStdString();

    IInteractive::ButtonDatas buttons;

    IInteractive::ButtonData saveAsBtn(SAVE_AS_BTN_ID, muse::trc("project/save", "Save as…"));
    saveAsBtn.role = IInteractive::ButtonRole::ContinueRole;
    buttons.push_back(saveAsBtn);

    IInteractive::ButtonData retryBtn(RETRY_SAVE_BTN_ID, muse::trc("project", "Try again"), true /*accent*/);
    retryBtn.role = IInteractive::ButtonRole::ContinueRole;
    buttons.push_back(retryBtn);

    IInteractive::ButtonData cancelBtn = interactive()->buttonData(IInteractive::Button::Cancel);
    buttons.push_back(cancelBtn);

    return interactive()->error(title, IInteractive::Text(body, IInteractive::TextFormat::RichText), buttons, retryBtn.btn)
           .then<int>(this, [](const IInteractive::Result& res, auto resolve) {
        return resolve(res.button());
    });
}

Promise<Ret> SaveProjectScenario::askToRevertCorruptedScoreToLastSaved()
{
    TRACEFUNC;

    std::string title = muse::trc("project", "Revert to last saved?");
    std::string body = muse::trc("project", "Your changes will be lost. This action cannot be undone.");

    return interactive()->warning(title, body, {
        { IInteractive::Button::No, IInteractive::Button::Yes }
    }, IInteractive::Button::Yes, IInteractive::Option::WithIcon)
           .then<Ret>(this, [this](const IInteractive::Result& res, auto resolve) {
        if (res.isButton(IInteractive::Button::No)) {
            return resolve(make_ret(Ret::Code::Cancel));
        }

        openProjectScenario()->revertToLastSaved().onResolve(this, [resolve](const Ret& ret) {
            if (!ret) {
                LOGE() << "score was not reverted: " << ret.toString();
            }

            (void)resolve(ret);
        });

        return Promise<Ret>::dummy_result();
    });
}

RecentFile SaveProjectScenario::makeRecentFile(INotationProjectPtr project)
{
    RecentFile file;
    file.path = project->path();

    if (project->isCloudProject()) {
        file.displayNameOverride = project->cloudInfo().name;
    }

    return file;
}

Promise<RetVal<SaveLocation> > SaveProjectScenario::askSaveLocation(INotationProjectPtr project, SaveMode mode,
                                                                    SaveLocationType preselectedType) const
{
    (void)preselectedType;
    return askSaveLocationOfType(project, mode, SaveLocationType::Local);
}

Promise<RetVal<SaveLocation> > SaveProjectScenario::askSaveLocationOfType(INotationProjectPtr project, SaveMode mode,
                                                                          SaveLocationType type) const
{
    if (type != SaveLocationType::Local) {
        return resolvedPromise(RetVal<SaveLocation>(make_ret(Ret::Code::NotSupported)));
    }

    configuration()->setLastUsedSaveLocationType(SaveLocationType::Local);
    return askLocalPath(project, mode)
           .then<RetVal<SaveLocation> >(this, [](const RetVal<muse::io::path_t>& path, auto resolve) {
        if (path.ret) {
            return resolve(RetVal<SaveLocation>::make_ok(SaveLocation(path.val)));
        }
        return resolve(RetVal<SaveLocation>(path.ret));
    });
}

Promise<RetVal<muse::io::path_t> > SaveProjectScenario::askLocalPath(INotationProjectPtr project, SaveMode saveMode) const
{
    std::string dialogTitle = muse::trc("project/save", "Save score");
    std::string filenameAddition;

    if (saveMode == SaveMode::SaveCopy) {
        //: used to form a filename suggestion, like "originalFile - copy"
        filenameAddition = " - " + muse::trc("project/save", "copy", "a copy of a file");
    } else if (saveMode == SaveMode::SaveSelection) {
        //: used to form a filename suggestion, like "originalFile - selection"
        filenameAddition = " - " + muse::trc("project/save", "selection");
    }

    muse::io::path_t defaultPath = configuration()->defaultSavingFilePath(project, filenameAddition);

    std::vector<std::string> filter {
        muse::trc("project", "DB Score 文件") + " (*.db)",
        muse::trc("project", "未压缩 DB Score 文件夹 [实验性]")
#ifdef Q_OS_MAC
        + " (*)"
#else
        + " (*.)"
#endif
    };

    return interactive()->selectSavingFile(dialogTitle, defaultPath, filter)
           .then<RetVal<muse::io::path_t> >(this, [this](const muse::io::path_t& path, auto resolve, auto) {
        muse::io::path_t selectedPath = path;

        if (selectedPath.empty()) {
            return resolve(RetVal<muse::io::path_t>(make_ret(Ret::Code::Cancel)));
        }

        if (!engraving::isMuseScoreFile(io::suffix(selectedPath))) {
            // Then it must be that the user is trying to save a mscx file.
            // At the selected path, a folder will be created,
            // and inside the folder, a mscx file will be created.
            // We should return the path to the mscx file.
            selectedPath = selectedPath.appendingComponent(io::filename(selectedPath)).appendingSuffix(engraving::MSCX);
        }

        configuration()->setLastSavedProjectsPath(io::dirpath(selectedPath));

        return resolve(RetVal<muse::io::path_t>::make_ok(selectedPath));
    }, [](int code, const std::string& err, auto resolve, auto) {
        //! NOTE Choosing nothing is not an error to report
        if (code == int(Ret::Code::Cancel)) {
            return resolve(RetVal<muse::io::path_t>(make_ret(Ret::Code::Cancel)));
        }

        return resolve(RetVal<muse::io::path_t>(muse::make_ret(code, err)));
    });
}
