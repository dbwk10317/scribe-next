// Deterministic command/status publication check; no transport or production data.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "common.h"
#include <thread>
#include <mutex>
#include <condition_variable>
#include <chrono>
#include <iostream>
#define private public
#include "store_queue.h"
#undef private
std::shared_ptr<DummyHandler> g_Handler(new DummyHandler);
static std::mutex state;
static std::condition_variable changed;
static bool configuring=false,published=false,release_configure=false,query_arrived=false,early_status=false;
static pthread_mutex_t* command_mutex=nullptr;
static thread_local bool querying=false;
extern "C" int __real_pthread_mutex_lock(pthread_mutex_t*);
extern "C" int __wrap_pthread_mutex_lock(pthread_mutex_t* mutex){
 if(querying && mutex==command_mutex){std::lock_guard<std::mutex> lock(state);query_arrived=true;changed.notify_all();}
 return __real_pthread_mutex_lock(mutex);
}
void fixture_configure(){std::unique_lock<std::mutex> lock(state);configuring=true;changed.notify_all();if(!changed.wait_for(lock,std::chrono::seconds(3),[]{return release_configure;}))std::abort();published=true;}
std::string fixture_status(){std::lock_guard<std::mutex> lock(state);early_status=!published;query_arrived=true;changed.notify_all();return published?"":"partial configuration";}
int main(){
 StoreQueue queue("fixture","fixture",1);command_mutex=&queue.cmdMutex;
 queue.configureAndOpen(pStoreConf(new StoreConf));
 {std::unique_lock<std::mutex> lock(state);if(!changed.wait_for(lock,std::chrono::seconds(3),[]{return configuring;}))std::abort();}
 std::string status;std::thread query([&]{querying=true;status=queue.getStatus();});
 {std::unique_lock<std::mutex> lock(state);if(!changed.wait_for(lock,std::chrono::seconds(3),[]{return query_arrived;}))std::abort();release_configure=true;changed.notify_all();}
 query.join();queue.stop();std::cout<<"early_status="<<early_status<<" status="<<status<<std::endl;
 return early_status||!status.empty()?1:0;
}
