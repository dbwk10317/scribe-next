// Allocation failure inside the actual addMessage; the message mutex must not stay held.
// Licensed under the Apache License, Version 2.0; see LICENSE.
#include "common.h"
#include <mutex>
#include <condition_variable>
#include <chrono>
#include <iostream>
#include <new>
#define private public
#include "store_queue.h"
#undef private
// The worker is parked inside its configure call (holding cmdMutex, never msgMutex) while this
// thread probes msgMutex, so a trylock failure can only mean this thread still holds it.
static std::mutex state;
static std::condition_variable changed;
static bool configuring=false,release_configure=false;
void fixture_configure(){std::unique_lock<std::mutex> lock(state);configuring=true;changed.notify_all();if(!changed.wait_for(lock,std::chrono::seconds(3),[]{return release_configure;}))std::abort();}
std::string fixture_status(){return "";}
// GNU link wrapping fails one allocation on the calling thread only; the worker is untouched.
static thread_local bool fail_next=false;
extern "C" void* __real__Znwm(std::size_t);
extern "C" void* __wrap__Znwm(std::size_t size){if(fail_next){fail_next=false;throw std::bad_alloc();}return __real__Znwm(size);}
int main(){
 ScribeContext context;StoreQueue queue(context,"fixture","fixture",1);
 queue.configureAndOpen(pStoreConf(new StoreConf));
 {std::unique_lock<std::mutex> lock(state);if(!changed.wait_for(lock,std::chrono::seconds(3),[]{return configuring;}))std::abort();}
 logentry_ptr_t entry(new scribe::thrift::LogEntry{"payload"});
 bool threw=false;
 fail_next=true; // first allocation after arming is msgQueue->push_back growing the vector under msgMutex
 try{queue.addMessage(entry);}catch(const std::bad_alloc&){threw=true;}
 fail_next=false;
 const bool held=pthread_mutex_trylock(&queue.msgMutex)!=0;
 pthread_mutex_unlock(&queue.msgMutex); // owned by this thread either way: trylock succeeded, or the pre-fix witness left it held
 bool accepted=false;
 if(!held){queue.addMessage(entry);accepted=queue.getSize()==7;} // worker still parked, so nothing drains the queue
 {std::lock_guard<std::mutex> lock(state);release_configure=true;changed.notify_all();}
 queue.stop();
 std::cout<<"threw="<<threw<<" held="<<held<<" accepted="<<accepted<<std::endl;
 return threw&&!held&&accepted?0:1;
}
