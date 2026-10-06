// Actual queue snapshots with concurrent writers; no daemon or network.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "common.h"
#include "store_queue.h"
#include <atomic>
#include <thread>
#include <iostream>
std::shared_ptr<DummyHandler> g_Handler(new DummyHandler);
void fixture_configure(){}
std::string fixture_status(){return "";}
int main(int argc,char**){
 StoreQueue queue("fixture","fixture",1);std::atomic<bool> ready(false),done(false);
 std::thread writer([&]{while(!ready.load()){}for(int i=0;i<10000;++i){logentry_ptr_t entry(new scribe::thrift::LogEntry);entry->message="data";queue.addMessage(entry);}done.store(true);});
 std::thread configurer([&]{while(!ready.load()){}for(int i=0;i<1000;++i){pStoreConf conf(new StoreConf);conf->configuredTarget=true;conf->target=(i%2)?1:65536;queue.configureAndOpen(conf);}});
 ready.store(true);bool invalid=false;while(!done.load()){if(argc==1 && queue.getSize()>40000)invalid=true;}
 writer.join();configurer.join();queue.stop();if(queue.getSize()!=0)invalid=true;
 std::cout<<"snapshot_bounds="<<!invalid<<" final_bytes="<<queue.getSize()<<std::endl;return invalid?1:0;
}
