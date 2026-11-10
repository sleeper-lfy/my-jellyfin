package net.lumen.media;

/** A filter-sheet draft. The page changes only when the draft is applied. */
final class DiscoveryFilters {
    String tag="",actor="",yearMin="",yearMax="",ratingMin="",tagsAll="",tagsAny="",tagsNot="",watch="",provider="",searchTag="";
    boolean favorite,wanted,disliked,online,hasResults;
    DiscoveryFilters copy(){
        DiscoveryFilters value=new DiscoveryFilters();
        value.tag=tag;value.actor=actor;value.yearMin=yearMin;value.yearMax=yearMax;value.ratingMin=ratingMin;
        value.tagsAll=tagsAll;value.tagsAny=tagsAny;value.tagsNot=tagsNot;value.watch=watch;value.provider=provider;
        value.searchTag=searchTag;value.hasResults=hasResults;value.favorite=favorite;value.wanted=wanted;value.disliked=disliked;value.online=online;return value;
    }
}
