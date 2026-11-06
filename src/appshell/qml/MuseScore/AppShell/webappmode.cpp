/*
 * SPDX-License-Identifier: GPL-3.0-only
 */

#include "webappmode.h"

#include <QCoreApplication>
#include <QUrlQuery>

#include <string>

#ifdef Q_OS_WASM
#include <emscripten/val.h>
#endif

using namespace mu::appshell;

static QString detectProductMode()
{
    const QString environmentMode = qEnvironmentVariable("DB_PRODUCT_MODE");
    if (!environmentMode.isEmpty()) {
        return environmentMode;
    }

#ifdef Q_OS_WASM
    const emscripten::val searchValue = emscripten::val::global("location")["search"];
    if (searchValue.isString()) {
        const QString search = QString::fromStdString(searchValue.as<std::string>());
        const QString mode = QUrlQuery(search.mid(search.startsWith(QLatin1Char('?')) ? 1 : 0))
                                 .queryItemValue(QStringLiteral("mode"));
        if (!mode.isEmpty()) {
            return mode;
        }
    }

    const emscripten::val mode = emscripten::val::global("DB_PRODUCT_MODE");
    if (!mode.isUndefined() && !mode.isNull()) {
        return QString::fromStdString(mode.as<std::string>());
    }
#endif

    const QString prefix("--db-product-mode=");
    for (const QString& argument : QCoreApplication::arguments()) {
        if (argument.startsWith(prefix)) {
            return argument.mid(prefix.size());
        }
    }
    return {};
}

WebAppMode::WebAppMode(QObject* parent)
    : QObject(parent), m_productMode(detectProductMode())
{
}

QString WebAppMode::productMode() const
{
    return m_productMode;
}

bool WebAppMode::studioPlayerMode() const
{
    return m_productMode == QStringLiteral("studio-player");
}
