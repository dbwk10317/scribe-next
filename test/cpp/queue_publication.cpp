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
// While the worker is parked inside configure (holding cmdMutex), getStatus must answer "" at once
// without locking cmdMutex or reading the store; once the worker published, it returns the store's.
static std::mutex state;
static std::condition_variable changed;
static bool configuring=false,release_configure=false,query_done=false,query_locked=false,store_read=false;
static pthread_mutex_t* command_mutex=nullptr;
static thread_local bool querying=false;
extern "C" int __real_pthread_mutex_lock(pthread_mutex_t*);
extern "C" int __wrap_pthread_mutex_lock(pthread_mutex_t* mutex){
 if(querying && mutex==command_mutex){std::lock_guard<std::mutex> lock(state);query_locked=true;changed.notify_all();}
 return __real_pthread_mutex_lock(mutex);
}
void fixture_configure(){std::unique_lock<std::mutex> lock(state);configuring=true;changed.notify_all();if(!changed.wait_for(lock,std::chrono::seconds(3),[]{return release_configure;}))std::abort();}
std::string fixture_status(){std::lock_guard<std::mutex> lock(state);if(!release_configure)store_read=true;return "configured";}
static std::string published_status(StoreQueue& queue){ // the worker publishes right after configure/open returns
 std::string status;auto end=std::chrono::steady_clock::now()+std::chrono::seconds(3);
 while((status=queue.getStatus()).empty()&&std::chrono::steady_clock::now()<end)std::this_thread::yield();
 return status;
}
int main(){
 ScribeContext context;StoreQueue queue(context,"fixture","fixture",1);command_mutex=&queue.cmdMutex;
 queue.configureAndOpen(pStoreConf(new StoreConf));
 {std::unique_lock<std::mutex> lock(state);if(!changed.wait_for(lock,std::chrono::seconds(3),[]{return configuring;}))std::abort();}
 std::string early="unset";std::thread query([&]{querying=true;early=queue.getStatus();std::lock_guard<std::mutex> lock(state);query_done=true;changed.notify_all();});
 {std::unique_lock<std::mutex> lock(state);if(!changed.wait_for(lock,std::chrono::seconds(3),[]{return query_done||query_locked;}))std::abort();release_configure=true;changed.notify_all();}
 query.join();const std::string late=published_status(queue);queue.stop();
 // A queue copied from a model gets only CMD_OPEN; its status must still be published.
 std::shared_ptr<StoreQueue> model(new StoreQueue(context,"fixture","model",1,true));
 StoreQueue copy(model,"copy");copy.open();const std::string copied=published_status(copy);copy.stop();
 std::cout<<"early_status="<<early<<" locked="<<query_locked<<" store_read="<<store_read<<" late_status="<<late<<" copy_status="<<copied<<std::endl;
 return early.empty()&&!query_locked&&!store_read&&late=="configured"&&copied=="configured"?0:1;
}
