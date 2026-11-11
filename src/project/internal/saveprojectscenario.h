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

#pragma once

#include "isaveprojectscenario.h"

#include <QString>

#include "modularity/ioc.h"
#include "async/asyncable.h"
#include "async/promise.h"
#include "interactive/iinteractive.h"
#include "interactive/iplatforminteractive.h"
#include "context/iglobalcontext.h"
#include "cloud/dbscoreauthorization/idbscoreauthorizationservice.h"

#include "iprojectconfiguration.h"
#include "irecentfilescontroller.h"
#include "iopenprojectscenario.h"

namespace mu::project {
class SaveProjectScenario : public ISaveProjectScenario, public muse::Contextable, public muse::async::Asyncable
{
    friend class SaveProjectScenarioTests;

public:
    muse::GlobalInject<IProjectConfiguration> configuration;
    muse::GlobalInject<muse::cloud::IDbScoreAuthorizationService> authorization;
    muse::GlobalInject<muse::IPlatformInteractive> platformInteractive;
    muse::ContextInject<IRecentFilesController> recentFilesController = { this };
    muse::ContextInject<muse::IInteractive> interactive = { this };
    muse::ContextInject<context::IGlobalContext> globalContext = { this };
    muse::ContextInject<IOpenProjectScenario> openProjectScenario = { this };

    SaveProjectScenario(const muse::modularity::ContextPtr& iocCtx)
        : muse::Contextable(iocCtx) {}

    muse::async::Promise<muse::Ret> saveProject(SaveMode saveMode, SaveLocationType saveLocationType = SaveLocationType::Undefined,
                                                bool force = false) override;
    muse::async::Promise<muse::Ret> saveProject(const muse::io::path_t& path = muse::io::path_t()) override;
    muse::async::Promise<muse::Ret> saveProjectAt(const muse::rcommand::Params& params) override;

    muse::async::Promise<muse::Ret> publish() override;
    muse::async::Promise<muse::Ret> shareAudio() override;

    bool isBusy(BusyStatus status) const override;
    muse::async::Notification busyChanged() const override;

private:
    INotationProjectPtr currentNotationProject() const;
    notation::INotationInteractionPtr currentInteraction() const;
    bool ensureCanSaveProFeatures(const INotationProjectPtr& project);

    void setBusy(BusyStatus status, bool isBusy);
    muse::async::Promise<muse::Ret> runIfNotBusy(BusyStatus status, const std::function<muse::async::Promise<muse::Ret>()>& flow);

    muse::async::Promise<bool> refuseSaveAfter(muse::async::Promise<muse::Ret> shown);

    muse::async::Promise<muse::RetVal<SaveLocation> > askSaveLocation(INotationProjectPtr project, SaveMode mode,
                                                                      SaveLocationType preselectedType = SaveLocationType::Undefined) const;
    muse::async::Promise<muse::RetVal<SaveLocation> > askSaveLocationOfType(INotationProjectPtr project, SaveMode mode,
                                                                            SaveLocationType type) const;
    muse::async::Promise<muse::RetVal<muse::io::path_t> > askLocalPath(INotationProjectPtr project, SaveMode mode) const;

    muse::Ret canSaveProject() const;
    muse::async::Promise<muse::Ret> saveProjectAt(const SaveLocation& saveLocation, SaveMode saveMode = SaveMode::Save, bool force = false);
    muse::async::Promise<muse::Ret> doSaveProjectAt(const SaveLocation& saveLocation, SaveMode saveMode);
    muse::async::Promise<muse::Ret> saveProjectLocally(const muse::io::path_t& path, SaveMode saveMode = SaveMode::Save,
                                                       bool createBackup = true);

    muse::async::Promise<bool> askIfUserAgreesToSaveProjectWithErrors(const muse::Ret& ret, const SaveLocation& location);
    muse::async::Promise<bool> askIfUserAgreesToSaveCorruptedScore(const SaveLocation& location, const std::string& errorText,
                                                                   bool newlyCreated);
    muse::async::Promise<bool> askIfUserAgreesToSaveCorruptedScoreLocally(const std::string& errorText, bool canRevert);
    muse::async::Promise<bool> askIfUserAgreesToSaveCorruptedScoreUponOpenning(const SaveLocation& location, const std::string& errorText);
    muse::async::Promise<muse::Ret> showErrCorruptedScoreCannotBeSaved(const SaveLocation& location, const std::string& errorText);

    muse::async::Promise<muse::Ret> warnScoreCouldnotBeSaved(const muse::Ret& ret);
    muse::async::Promise<muse::Ret> warnScoreCouldnotBeSaved(const std::string& errorText);
    muse::async::Promise<int> warnScoreHasBecomeCorruptedAfterSave(const muse::Ret& ret);

    muse::async::Promise<muse::Ret> askToRevertCorruptedScoreToLastSaved();

    RecentFile makeRecentFile(INotationProjectPtr project);

    std::set<BusyStatus> m_busyStatuses;
    muse::async::Notification m_busyChanged;
};
}
