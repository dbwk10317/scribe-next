// Minimal dependency boundary for actual StoreQueue synchronization tests.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#ifndef QUEUE_COMPONENT_COMMON_H
#define QUEUE_COMPONENT_COMMON_H
#include <algorithm>
#include <string>
#include <queue>
#include <vector>
#include <memory>
#include <stdexcept>
#include <cstdlib>
#include <pthread.h>
inline void LOG_OPER(const char*, ...) {}
namespace scribe { namespace thrift { struct LogEntry {std::string message;}; } }
typedef std::shared_ptr<scribe::thrift::LogEntry> logentry_ptr_t;
typedef std::vector<logentry_ptr_t> logentry_vector_t;
struct StoreConf {
 unsigned long long target=16384;
 bool configuredTarget=false;
 bool getUnsignedLongLong(const std::string& name,unsigned long long& value){
  if(configuredTarget && name=="target_write_size"){value=target;return true;}return false;
 }
 bool getUnsigned(const std::string&,unsigned long&){return false;}
 bool getString(const std::string&,std::string&){return false;}
};
typedef std::shared_ptr<StoreConf> pStoreConf;
class ScribeContext {public: void incCounter(const std::string&,const std::string&,size_t){}};
void fixture_configure();
inline unsigned long long fixture_handled_bytes=0; // written by the worker, read after stop() joined it
std::string fixture_status();
class StoreQueue;
struct Store {
 static std::shared_ptr<Store> createStore(ScribeContext&,StoreQueue*,const std::string&,const std::string&,bool,bool){return std::shared_ptr<Store>(new Store);}
 std::shared_ptr<Store> copy(const std::string&){return std::shared_ptr<Store>(new Store);}
 StoreQueue* queue=nullptr; void setStoreQueue(StoreQueue* q){queue=q;}
 void configure(pStoreConf,pStoreConf){fixture_configure();}
 std::string getStatus(){return fixture_status();}
 std::string getType(){return "fixture";}
 bool opened=false; // close() on a store that was never opened is a queue bug (a real BufferStore crashes)
 bool isOpen(){return false;} bool open(){opened=true;return true;} void close(){if(!opened)std::abort();}
 void periodicCheck(){} void flush(){}
 bool handleMessages(std::shared_ptr<logentry_vector_t> messages){for(auto& entry:*messages)fixture_handled_bytes+=entry->message.size();return true;}
};
#endif
