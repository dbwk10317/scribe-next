// scribe-next server context injected into stores, store queues, the connection pool and the bucket updater.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef SCRIBE_CONTEXT_H
#define SCRIBE_CONTEXT_H

#include "common.h"

class ConnPool;

// What those components use from the running server, which they used to read
// from process-wide globals. scribeHandler implements this interface, owns the
// connection pool and hands itself to the store queues it creates.
class ScribeContext {
 public:
  virtual ~ScribeContext() {}

  virtual void incCounter(std::string category, std::string counter) = 0;
  virtual void incCounter(std::string category, std::string counter, long amount) = 0;
  virtual void incCounter(std::string counter) = 0;
  virtual void incCounter(std::string counter, long amount) = 0;

  virtual unsigned long long getMaxQueueSize() = 0;
  virtual int getThriftMaxFrameSize() const = 0;
  virtual int getThriftMaxMessageSize() const = 0;
  virtual bool hasValidThriftLimits() const = 0;

  virtual ConnPool& getConnPool() = 0;
  virtual facebook::fb303::FacebookBase* getFacebookBase() = 0;
};

#endif // SCRIBE_CONTEXT_H
