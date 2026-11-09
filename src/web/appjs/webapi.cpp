/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2025 MuseScore Limited and others
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
#include "webapi.h"

#ifdef Q_OS_WASM
#include <emscripten/bind.h>
#include <emscripten/val.h>
#endif

#include <algorithm>
#include <unordered_map>
#include <QTimer>
#include <QString>

#include "global/io/file.h"
#include "log.h"

#include "engraving/dom/box.h"
#include "engraving/dom/masterscore.h"
#include "engraving/dom/measure.h"
#include "engraving/dom/measurebase.h"
#include "engraving/dom/mscore.h"
#include "engraving/dom/page.h"
#include "engraving/dom/score.h"
#include "engraving/dom/system.h"
#include "engraving/style/style.h"
#include "engraving/types/spatium.h"

#include "notation/inotation.h"
#include "notation/inotationelements.h"
#include "notation/inotationpainting.h"
#include "notation/inotationundostack.h"
#include "notation/inotationviewstate.h"
#include "notation/imasternotation.h"
#include "notation/types/viewmode.h"

using namespace muse;
using namespace mu::appjs;

namespace mu::appjs::detail {
struct PlayerLayoutState {
    struct BoxState {
        engraving::Box* box = nullptr;
        double height = 0.0;
        double topGap = 0.0;
        double bottomGap = 0.0;
        bool autoSize = true;
        bool visible = true;
        std::vector<std::pair<engraving::EngravingItem*, bool>> textItems;
    };

    struct BreakState {
        engraving::MeasureBase* item = nullptr;
        bool lineBreak = false;
        bool pageBreak = false;
        bool sectionBreak = false;
        bool noBreak = false;
        double measureStretch = 1.0;
    };

    engraving::Score* score = nullptr;
    double pageWidth = 0.0;
    double pageHeight = 0.0;
    double pagePrintableWidth = 0.0;
    double pageEvenLeftMargin = 0.0;
    double pageOddLeftMargin = 0.0;
    double pageEvenTopMargin = 0.0;
    double pageEvenBottomMargin = 0.0;
    double pageOddTopMargin = 0.0;
    double pageOddBottomMargin = 0.0;
    double spatium = 0.0;
    double staffUpperBorder = 0.0;
    double staffLowerBorder = 0.0;
    double minSystemDistance = 0.0;
    double maxSystemDistance = 0.0;
    double lastSystemFillLimit = 0.0;
    double tempoFontSize = 12.0;
    double tempoChangeFontSize = 12.0;
    double stickingFontSize = 10.0;
    bool firstSystemIndentation = false;
    bool generateClef = true;
    bool pageTwosided = false;
    bool verticalSpread = false;
    bool backgroundUseColor = true;
    QColor backgroundColor;
    QColor notationColor;
    bool showUnprintable = true;
    bool showFrames = true;
    int viewMode = 0;

    std::vector<BoxState> boxes;
    std::vector<BreakState> breaks;
    bool portraitApplied = false;
};
}

#ifdef Q_OS_WASM
static void callJsWithBytes(const char* fnname, const uint8_t* data, size_t size)
{
    emscripten::val jsArray = emscripten::val::global("Uint8Array").new_(
        emscripten::typed_memory_view(size, data)
        );

    emscripten::val::module_property(fnname)(jsArray);
}

#else

static void callJsWithBytes(const char*, const uint8_t*, size_t)
{
    NOT_SUPPORTED;
}

#endif

WebApi* WebApi::instance()
{
    static WebApi a;

    return &a;
}

WebApi::~WebApi() = default;

std::shared_ptr<mu::context::IGlobalContext> WebApi::globalContext() const
{
    return muse::modularity::ioc(m_context)->resolve<mu::context::IGlobalContext>("context");
}

std::shared_ptr<muse::IInteractive> WebApi::interactive() const
{
    return muse::modularity::ioc(m_context)->resolve<muse::IInteractive>("interactive");
}

std::shared_ptr<muse::actions::IActionsDispatcher> WebApi::dispatcher() const
{
    return muse::modularity::ioc(m_context)->resolve<muse::actions::IActionsDispatcher>("actions");
}

std::shared_ptr<mu::playback::IPlaybackController> WebApi::playbackController() const
{
    return muse::modularity::ioc(m_context)->resolve<mu::playback::IPlaybackController>("playback");
}

void WebApi::init(const muse::modularity::ContextPtr& context)
{
    m_context = context;
    auto appContext = globalContext();
    IF_ASSERT_FAILED(appContext) {
        return;
    }

    auto onProjectChanged = [this]() {
        if (m_currentProject) {
            m_currentProject->saveComplited().disconnect(this);
        }

        m_currentProject = globalContext()->currentProject();
        if (m_playerLayoutState
            && m_playerLayoutState->score
            != (m_currentProject && m_currentProject->masterNotation()
                ? static_cast<engraving::Score*>(m_currentProject->masterNotation()->masterScore())
                : nullptr)) {
            m_playerLayoutState.reset();
        }

        if (m_currentProject) {
            m_currentProject->saveComplited().onReceive(this, [this](const muse::io::path_t& path, project::SaveMode mode) {
                onProjectSaved(path, mode);
            });
        }
    };

    appContext->currentProjectChanged().onNotify(this, onProjectChanged);

    onProjectChanged();
}

void WebApi::deinit()
{
    if (m_currentProject) {
        m_currentProject->saveComplited().disconnect(this);
    }
}

void WebApi::load(const void* source, unsigned int len)
{
    LOGI() << source << ", len: " << len;
    ByteArray data(reinterpret_cast<const uint8_t*>(source), len);
    const io::path_t tempFilePath = "/current.mscz";

    io::File::remove(tempFilePath);

    if (!io::File::writeFile(tempFilePath, data) || !io::File::exists(tempFilePath)) {
        LOGE() << "failed write temporary score: " << tempFilePath;
        return;
    }

    dispatcher()->dispatch("file-open", actions::ActionData::make_arg1(QUrl::fromLocalFile(tempFilePath.toQString())));
}

void WebApi::addSoundFont(const std::string& uri)
{
    soundFontController()->addSoundFont(Uri(uri));
}

void WebApi::startAudioProcessing()
{
    startAudioController()->startAudioProcessing(IApplication::RunMode::GuiApp);
}

void WebApi::togglePlayback()
{
    const auto context = globalContext();
    IF_ASSERT_FAILED(context && context->playbackState()) {
        return;
    }

    const auto playback = playbackController();
    IF_ASSERT_FAILED(playback) {
        return;
    }

    if (context->playbackState()->isPlaying()) {
        playback->pause();
    } else {
        playback->play();
    }
}

int WebApi::playbackState() const
{
    int state = 0;
    const auto context = globalContext();
    const auto playback = playbackController();

    if (playback && playback->isPlaybackInited()) {
        state |= 1;
    }
    if (playback && playback->isPlayAllowed()) {
        state |= 2;
    }
    if (context && context->currentNotation()) {
        state |= 4;
    }
    if (playback && playback->isPlaying()) {
        state |= 8;
    }

    return state;
}

int WebApi::scoreRevision() const
{
    const auto context = globalContext();
    if (!context || !context->currentNotation()) {
        return -1;
    }

    const auto undoStack = context->currentNotation()->undoStack();
    if (!undoStack) {
        return -1;
    }

    return static_cast<int>(undoStack->currentStateIndex());
}

std::string WebApi::playerLayoutDiagnostics() const
{
    const auto context = globalContext();
    if (!context || !context->currentNotation()) {
        return "{}";
    }

    const engraving::Score* score = context->currentNotation()->elements()->msScore();
    if (!score) {
        return "{}";
    }

    const int pages = static_cast<int>(score->npages());
    const int systems = pages > 0 ? static_cast<int>(score->pages().front()->systems().size()) : 0;
    const int measures = systems > 0
                         ? static_cast<int>(score->pages().front()->system(0)->measures().size())
                         : 0;
    const engraving::MStyle& style = score->style();
    const double pageWidthMm = style.styleD(engraving::Sid::pageWidth) * 25.4;
    const double pageHeightMm = style.styleD(engraving::Sid::pageHeight) * 25.4;
    const double printableWidthMm = style.styleD(engraving::Sid::pagePrintableWidth) * 25.4;
    const double spatiumMm = style.styleD(engraving::Sid::spatium) / engraving::DPMM;
    double systemPitch = 0.0;
    if (pages > 0) {
        const std::vector<engraving::System*>& pageSystems = score->pages().front()->systems();
        if (pageSystems.size() > 1) {
            systemPitch = pageSystems[1]->y() - pageSystems[0]->y();
        }
    }

    return QStringLiteral(
        "{\"pages\":%1,\"systems\":%2,\"measures\":%3,"
        "\"pageWidthMm\":%4,\"pageHeightMm\":%5,"
        "\"printableWidthMm\":%6,\"spatiumMm\":%7,\"systemPitch\":%8}")
        .arg(pages)
        .arg(systems)
        .arg(measures)
        .arg(pageWidthMm, 0, 'f', 3)
        .arg(pageHeightMm, 0, 'f', 3)
        .arg(printableWidthMm, 0, 'f', 3)
        .arg(spatiumMm, 0, 'f', 3)
        .arg(systemPitch, 0, 'f', 3)
        .toStdString();
}

bool WebApi::setPlayerLayout(const std::string& layout, int viewportWidth, int viewportHeight)
{
    const auto context = globalContext();
    if (!context || !context->currentNotation()) {
        return false;
    }

    notation::INotationPtr notation = context->currentNotation();
    engraving::Score* score = notation->elements()->msScore();
    if (!score) {
        return false;
    }

    if (!m_playerLayoutState || m_playerLayoutState->score != score) {
        auto state = std::make_unique<detail::PlayerLayoutState>();
        state->score = score;

        const engraving::MStyle& style = score->style();
        state->pageWidth = style.styleD(engraving::Sid::pageWidth);
        state->pageHeight = style.styleD(engraving::Sid::pageHeight);
        state->pagePrintableWidth = style.styleD(engraving::Sid::pagePrintableWidth);
        state->pageEvenLeftMargin = style.styleD(engraving::Sid::pageEvenLeftMargin);
        state->pageOddLeftMargin = style.styleD(engraving::Sid::pageOddLeftMargin);
        state->pageEvenTopMargin = style.styleD(engraving::Sid::pageEvenTopMargin);
        state->pageEvenBottomMargin = style.styleD(engraving::Sid::pageEvenBottomMargin);
        state->pageOddTopMargin = style.styleD(engraving::Sid::pageOddTopMargin);
        state->pageOddBottomMargin = style.styleD(engraving::Sid::pageOddBottomMargin);
        state->spatium = style.styleD(engraving::Sid::spatium);
        state->staffUpperBorder = style.styleAbsolute(engraving::Sid::staffUpperBorder);
        state->staffLowerBorder = style.styleAbsolute(engraving::Sid::staffLowerBorder);
        state->minSystemDistance = style.styleAbsolute(engraving::Sid::minSystemDistance);
        state->maxSystemDistance = style.styleAbsolute(engraving::Sid::maxSystemDistance);
        state->lastSystemFillLimit = style.styleD(engraving::Sid::lastSystemFillLimit);
        state->tempoFontSize = style.styleD(engraving::Sid::tempoFontSize);
        state->tempoChangeFontSize = style.styleD(engraving::Sid::tempoChangeFontSize);
        state->stickingFontSize = style.styleD(engraving::Sid::stickingFontSize);
        state->firstSystemIndentation = style.styleB(engraving::Sid::enableIndentationOnFirstSystem);
        state->generateClef = style.styleB(engraving::Sid::genClef);
        state->pageTwosided = style.styleB(engraving::Sid::pageTwosided);
        state->verticalSpread = style.styleB(engraving::Sid::enableVerticalSpread);
        state->backgroundUseColor = notationConfiguration()->backgroundUseColor();
        state->backgroundColor = notationConfiguration()->backgroundColor();
        state->notationColor = notationConfiguration()->notationColor();
        state->showUnprintable = score->showUnprintable();
        state->showFrames = score->showFrames();
        state->viewMode = static_cast<int>(notation->viewMode());

        for (engraving::MeasureBase* item = score->first(); item && !item->isMeasure(); item = item->next()) {
            if (!item->isBox()) {
                continue;
            }
            engraving::Box* box = static_cast<engraving::Box*>(item);
            state->boxes.push_back({ box, box->boxHeight().val(), box->topGap().val(), box->bottomGap().val(),
                                     box->isAutoSizeEnabled(), box->visible() });
            for (engraving::EngravingItem* child : box->childrenItems(true)) {
                if (child->isTextBase()) {
                    state->boxes.back().textItems.emplace_back(child, child->visible());
                }
            }
        }

        for (engraving::MeasureBase* item = score->first(); item; item = item->next()) {
            const double measureStretch = item->isMeasure()
                                          ? static_cast<engraving::Measure*>(item)->userStretch()
                                          : 1.0;
            state->breaks.push_back({ item, item->lineBreak(), item->pageBreak(), item->sectionBreak(),
                                      item->noBreak(), measureStretch });
        }

        m_playerLayoutState = std::move(state);
    }

    detail::PlayerLayoutState& state = *m_playerLayoutState;
    const bool portrait = layout == "portrait";
    bool changed = false;
    if (portrait && !state.portraitApplied) {
        constexpr double MM_TO_INCH = 1.0 / 25.4;
        constexpr double PLAYER_PORTRAIT_BOTTOM_PADDING_MM = 34.0;
        const double pageWidthMm = 70.0;
        constexpr int PLAYER_CHROME_HEIGHT = 60;
        const int scoreViewportHeight = viewportHeight > PLAYER_CHROME_HEIGHT
                                        ? viewportHeight - PLAYER_CHROME_HEIGHT
                                        : viewportHeight;
        const double aspect = viewportWidth > 0 && scoreViewportHeight > 0
                              ? static_cast<double>(scoreViewportHeight) / viewportWidth
                              : 844.0 / 390.0;
        int measureCount = 0;
        for (const detail::PlayerLayoutState::BreakState& item : state.breaks) {
            if (item.item->isMeasure()) {
                ++measureCount;
            }
        }
        const double pageHeightMm = std::max(
            pageWidthMm * aspect,
            static_cast<double>(measureCount) * 30.0 + PLAYER_PORTRAIT_BOTTOM_PADDING_MM);
        constexpr double spatiumMm = 2.33;
        const double spatiumUnits = spatiumMm * engraving::DPMM;
        const double printableWidthUnits = (pageWidthMm - 3.6) * MM_TO_INCH * engraving::DPI;

        for (const detail::PlayerLayoutState::BoxState& boxState : state.boxes) {
            boxState.box->setVisible(false);
            boxState.box->setAutoSizeEnabled(false);
            boxState.box->setBoxHeight(engraving::Spatium(0.0));
            boxState.box->setTopGap(engraving::Spatium(0.0));
            boxState.box->setBottomGap(engraving::Spatium(0.0));
            for (const auto& textItem : boxState.textItems) {
                textItem.first->setVisible(false);
            }
        }

        std::unordered_map<engraving::Sid, engraving::PropertyValue> styles;
        styles.emplace(engraving::Sid::pageWidth, pageWidthMm * MM_TO_INCH);
        styles.emplace(engraving::Sid::pageHeight, pageHeightMm * MM_TO_INCH);
        styles.emplace(engraving::Sid::pagePrintableWidth, (pageWidthMm - 3.6) * MM_TO_INCH);
        styles.emplace(engraving::Sid::pageEvenLeftMargin, 1.8 * MM_TO_INCH);
        styles.emplace(engraving::Sid::pageOddLeftMargin, 1.8 * MM_TO_INCH);
        styles.emplace(engraving::Sid::pageEvenTopMargin, 0.7 * MM_TO_INCH);
        styles.emplace(engraving::Sid::pageEvenBottomMargin, 1.8 * MM_TO_INCH);
        styles.emplace(engraving::Sid::pageOddTopMargin, 0.7 * MM_TO_INCH);
        styles.emplace(engraving::Sid::pageOddBottomMargin, 1.8 * MM_TO_INCH);
        styles.emplace(engraving::Sid::pageTwosided, false);
        styles.emplace(engraving::Sid::spatium, spatiumUnits);
        styles.emplace(engraving::Sid::staffUpperBorder, engraving::Spatium(0.5));
        styles.emplace(engraving::Sid::staffLowerBorder, engraving::Spatium(0.5));
        styles.emplace(engraving::Sid::minSystemDistance, engraving::Spatium(3.5));
        styles.emplace(engraving::Sid::maxSystemDistance, engraving::Spatium(4.0));
        styles.emplace(engraving::Sid::enableVerticalSpread, false);
        styles.emplace(engraving::Sid::minMeasureWidth, engraving::Spatium(printableWidthUnits / spatiumUnits));
        styles.emplace(engraving::Sid::lastSystemFillLimit, 0.0);
        styles.emplace(engraving::Sid::tempoFontSize, std::max(7.0, state.tempoFontSize - 3.0));
        styles.emplace(engraving::Sid::tempoChangeFontSize, std::max(
                           7.0, state.tempoChangeFontSize - 3.0));
        styles.emplace(engraving::Sid::stickingFontSize, std::max(
                           7.0, state.stickingFontSize - 3.0));
        styles.emplace(engraving::Sid::enableIndentationOnFirstSystem, false);
        styles.emplace(engraving::Sid::genClef, false);
        score->undoChangeStyleValues(std::move(styles));
        for (const detail::PlayerLayoutState::BreakState& item : state.breaks) {
            if (item.item->isMeasure()) {
                static_cast<engraving::Measure*>(item.item)->setUserStretch(3.0);
            }
        }
        notationConfiguration()->setBackgroundUseColor(true);
        notationConfiguration()->setBackgroundColor(Qt::white);
        notationConfiguration()->setNotationColor(Qt::black);
        notationConfiguration()->setPlaybackCursorLength(0.7);
        score->setShowUnprintable(false);
        score->setShowFrames(false);

        state.portraitApplied = true;
        changed = true;
    } else if (!portrait && state.portraitApplied) {
        for (const detail::PlayerLayoutState::BoxState& boxState : state.boxes) {
            boxState.box->setVisible(boxState.visible);
            boxState.box->setAutoSizeEnabled(boxState.autoSize);
            boxState.box->setBoxHeight(engraving::Spatium::fromAbsolute(boxState.height, state.spatium));
            boxState.box->setTopGap(engraving::Spatium::fromAbsolute(boxState.topGap, state.spatium));
            boxState.box->setBottomGap(engraving::Spatium::fromAbsolute(boxState.bottomGap, state.spatium));
            for (const auto& textItem : boxState.textItems) {
                textItem.first->setVisible(textItem.second);
            }
        }

        std::unordered_map<engraving::Sid, engraving::PropertyValue> styles;
        styles.emplace(engraving::Sid::pageWidth, state.pageWidth);
        styles.emplace(engraving::Sid::pageHeight, state.pageHeight);
        styles.emplace(engraving::Sid::pagePrintableWidth, state.pagePrintableWidth);
        styles.emplace(engraving::Sid::pageEvenLeftMargin, state.pageEvenLeftMargin);
        styles.emplace(engraving::Sid::pageOddLeftMargin, state.pageOddLeftMargin);
        styles.emplace(engraving::Sid::pageEvenTopMargin, state.pageEvenTopMargin);
        styles.emplace(engraving::Sid::pageEvenBottomMargin, state.pageEvenBottomMargin);
        styles.emplace(engraving::Sid::pageOddTopMargin, state.pageOddTopMargin);
        styles.emplace(engraving::Sid::pageOddBottomMargin, state.pageOddBottomMargin);
        styles.emplace(engraving::Sid::pageTwosided, state.pageTwosided);
        styles.emplace(engraving::Sid::spatium, state.spatium);
        styles.emplace(engraving::Sid::staffUpperBorder, engraving::Spatium::fromAbsolute(
                           state.staffUpperBorder, state.spatium));
        styles.emplace(engraving::Sid::staffLowerBorder, engraving::Spatium::fromAbsolute(
                           state.staffLowerBorder, state.spatium));
        styles.emplace(engraving::Sid::minSystemDistance, engraving::Spatium::fromAbsolute(
                           state.minSystemDistance, state.spatium));
        styles.emplace(engraving::Sid::maxSystemDistance, engraving::Spatium::fromAbsolute(
                           state.maxSystemDistance, state.spatium));
        styles.emplace(engraving::Sid::enableVerticalSpread, state.verticalSpread);
        styles.emplace(engraving::Sid::lastSystemFillLimit, state.lastSystemFillLimit);
        styles.emplace(engraving::Sid::tempoFontSize, state.tempoFontSize);
        styles.emplace(engraving::Sid::tempoChangeFontSize, state.tempoChangeFontSize);
        styles.emplace(engraving::Sid::stickingFontSize, state.stickingFontSize);
        styles.emplace(engraving::Sid::enableIndentationOnFirstSystem, state.firstSystemIndentation);
        styles.emplace(engraving::Sid::genClef, state.generateClef);
        score->undoChangeStyleValues(std::move(styles));
        notationConfiguration()->setBackgroundColor(state.backgroundColor);
        notationConfiguration()->setBackgroundUseColor(state.backgroundUseColor);
        notationConfiguration()->setNotationColor(state.notationColor);
        score->setShowUnprintable(state.showUnprintable);
        score->setShowFrames(state.showFrames);

        for (const detail::PlayerLayoutState::BreakState& item : state.breaks) {
            item.item->setLineBreak(item.lineBreak);
            item.item->setPageBreak(item.pageBreak);
            item.item->setSectionBreak(item.sectionBreak);
            item.item->setNoBreak(item.noBreak);
            if (item.item->isMeasure()) {
                static_cast<engraving::Measure*>(item.item)->setUserStretch(item.measureStretch);
            }
            item.item->cleanupLayoutBreaks(false);
        }
        state.portraitApplied = false;
        changed = true;
    }

    if (!changed) {
        return true;
    }

    const auto targetViewMode = portrait
                                ? notation::ViewMode::SYSTEM
                                : static_cast<notation::ViewMode>(state.viewMode);
    notation->viewState()->setViewMode(notation::ViewMode::LINE);
    notation->painting()->setViewMode(notation::ViewMode::LINE);
    notation->viewState()->setViewMode(targetViewMode);
    notation->painting()->setViewMode(targetViewMode);
    score->doLayout();
    score->update();

    if (!portrait) {
        QTimer::singleShot(120, [this]() {
            dispatcher()->dispatch(muse::actions::ActionCode("command://notation/view/zoom-to-page-width"));
        });
    }
    return true;
}

void WebApi::onProjectSaved(const muse::io::path_t& path, mu::project::SaveMode)
{
    IF_ASSERT_FAILED(io::File::exists(path)) {
        LOGE() << "file does not exist, path: " << path;
        return;
    }

    ByteArray data;
    Ret ret  = io::File::readFile(path, data);
    if (!ret) {
        LOGE() << "failed read file, path: " << path;
        return;
    }

    callJsWithBytes("onProjectSaved", data.constData(), data.size());
}
