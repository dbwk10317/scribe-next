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
#include <pthread.h>
#include <boost/shared_ptr.hpp>
inline void LOG_OPER(const char*, ...) {}
namespace scribe { namespace thrift { struct LogEntry {std::string message;}; } }
typedef boost::shared_ptr<scribe::thrift::LogEntry> logentry_ptr_t;
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
typedef boost::shared_ptr<StoreConf> pStoreConf;
struct DummyHandler {void incCounter(const std::string&,const std::string&,size_t){}};
extern std::shared_ptr<DummyHandler> g_Handler;
void fixture_configure();
std::string fixture_status();
class StoreQueue;
struct Store {
 static boost::shared_ptr<Store> createStore(StoreQueue*,const std::string&,const std::string&,bool,bool){return boost::shared_ptr<Store>(new Store);}
 boost::shared_ptr<Store> copy(const std::string&){return boost::shared_ptr<Store>(new Store);}
 void configure(pStoreConf,pStoreConf){fixture_configure();}
 std::string getStatus(){return fixture_status();}
 std::string getType(){return "fixture";}
 bool isOpen(){return false;} bool open(){return true;} void close(){}
 void periodicCheck(){} void flush(){}
 bool handleMessages(boost::shared_ptr<logentry_vector_t>){return true;}
};
#endif
