/* Host choice persistence. Does not access guest VM or gameplay save files. */
namespace {
struct ChoiceFile {
    int fd=-1;
    explicit ChoiceFile(int value):fd(value) {}
    ~ChoiceFile(){if(fd>=0) close(fd);}
    ChoiceFile(const ChoiceFile&)=delete;
};
std::string choice_error;
std::map<unsigned,nlohmann::json> remembered_entries;
bool persistent_choices()
{
    const char* value=std::getenv("D2_APPEARANCE_PERSIST");
    return value && std::string_view(value)=="1";
}
nlohmann::json class_entry(const nlohmann::json& data,unsigned cls)
{
    auto entries=data.contains("appearances")?data.at("appearances"):nlohmann::json::array({data});
    nlohmann::json result;
    for(const auto& entry:entries) if(entry.at("class_id")==cls) {
        if(!result.is_null()) throw std::runtime_error("Duplicate active class");
        result=entry;
    }
    if(result.is_null()) throw std::runtime_error("Missing active class");
    return result;
}
nlohmann::json class_catalog(const nlohmann::json& data,unsigned cls)
{
    auto result=nlohmann::json::array();
    for(const auto& item:data.at("costumes")) if(item.at("class_id")==cls) result.push_back(item);
    return result;
}
bool persist_choice(unsigned cls,std::string_view token)
{
    if(!persistent_choices()) return true;
    choice_error.clear();std::string temporary;
    try {
        const char* target=std::getenv("D2_APPEARANCE_PERSIST_PATH");
        if(!target || !*target) throw std::runtime_error("Missing private choice path");
        std::filesystem::path path=target;
        const auto& initial=registry().state.manifest;
        auto expected_root=std::filesystem::path(initial.at("runtime_environment").at("PS3_HDD0_ROOT").get<std::string>()).parent_path();
        if(!path.is_absolute() || path.parent_path()!=expected_root || path.filename().empty() ||
            std::filesystem::canonical(expected_root)!=expected_root)
            throw std::runtime_error("Choice path is outside the private profile");
        ChoiceFile directory(open(expected_root.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW));
        if(directory.fd<0) throw std::runtime_error("Cannot open private profile");
        ChoiceFile lock(openat(directory.fd,".appearance-choice.lock",O_CREAT|O_RDWR|O_CLOEXEC|O_NOFOLLOW,0600));
        struct stat info;
        if(lock.fd<0 || fstat(lock.fd,&info) || !S_ISREG(info.st_mode) || flock(lock.fd,LOCK_EX|LOCK_NB))
            throw std::runtime_error("Choice file is busy or unavailable");
        ChoiceFile input(openat(directory.fd,path.filename().c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW));
        if(input.fd<0 || fstat(input.fd,&info) || !S_ISREG(info.st_mode) || info.st_size<1 || info.st_size>1024*1024)
            throw std::runtime_error("Invalid private manifest");
        std::string bytes(size_t(info.st_size),'\0');size_t offset=0;
        while(offset<bytes.size()) {
            ssize_t got=read(input.fd,bytes.data()+offset,bytes.size()-offset);
            if(got<0 && errno==EINTR) continue;
            if(got<=0) throw std::runtime_error("Cannot read private manifest");
            offset+=size_t(got);
        }
        auto data=nlohmann::json::parse(bytes);
        if(data.at("mode")!=initial.at("mode") || data.at("runtime_environment")!=initial.at("runtime_environment") ||
           class_catalog(data,cls)!=class_catalog(initial,cls)) throw std::runtime_error("Profile catalog changed during play");
        auto current=class_entry(data,cls);
        auto expected=remembered_entries.contains(cls)?remembered_entries.at(cls):class_entry(initial,cls);
        if(current!=expected) throw std::runtime_error("Next-launch choice changed elsewhere");
        auto chosen=current;
        if(!token.empty()) {
            bool found=false;
            for(const auto& item:class_catalog(data,cls)) if(item.at("costume_id")==token) {
                if(found) throw std::runtime_error("Duplicate costume");
                found=true;
                for(const char* key:{"selector","new_resource","visual_class_id","selection_mode","costume_id","display_name","illustration_resource","illustration_donor","face_cell"}) {
                    chosen.erase(key);if(item.contains(key)) chosen[key]=item.at(key);
                }
            }
            if(!found) throw std::runtime_error("Unknown costume");
        }
        chosen["enabled"]=!token.empty();
        if(data.contains("appearances")) {
            for(auto& entry:data.at("appearances")) if(entry.at("class_id")==cls) entry=chosen;
        } else data=chosen;
        if(data.value("class_id",0u)==cls && !token.empty())
            for(const char* key:{"new_resource","visual_class_id","illustration_resource","illustration_donor","face_cell"}) {
                data.erase(key);if(chosen.contains(key)) data[key]=chosen.at(key);
            }
        std::string payload=data.dump(2)+"\n";
        if(payload.size()>1024*1024) throw std::runtime_error("Updated manifest is too large");
        temporary=(expected_root/".appearance-choice-XXXXXX").string();
        std::vector<char> name(temporary.begin(),temporary.end());name.push_back(0);
        ChoiceFile output(mkstemp(name.data()));temporary=name.data();
        if(output.fd<0) {temporary.clear();throw std::runtime_error("Cannot create choice update");}
        offset=0;
        while(offset<payload.size()) {
            ssize_t wrote=write(output.fd,payload.data()+offset,payload.size()-offset);
            if(wrote<0 && errno==EINTR) continue;
            if(wrote<=0) throw std::runtime_error("Cannot write choice update");
            offset+=size_t(wrote);
        }
        if(fsync(output.fd) || rename(temporary.c_str(),path.c_str())) throw std::runtime_error("Cannot publish choice update");
        temporary.clear();remembered_entries[cls]=chosen;
        std::fprintf(stderr,"[D2 appearance choice] remembered class=%u costume=%s path=%s\n",cls,
            token.empty()?"original":std::string(token).c_str(),path.c_str());
        return true;
    } catch(const std::exception& error) {
        if(!temporary.empty()) unlink(temporary.c_str());
        choice_error=error.what();
        std::fprintf(stderr,"[D2 appearance choice] persistence rejected: %s\n",choice_error.c_str());
        return false;
    }
}
}
