;(function () {
    "use strict";

    var elPlaylist = $el('playlist-items');
    var spinner = $el('playlist-spinner');
    var eventSource;
    var player;
    var playlist = [];
    var currentIndex = 0;
    var trackSet = {};
    var previousVideoState = -1;  // YT.PlayerState.UNSTARTED

    window.onYouTubeIframeAPIReady = function () {
        player = new YT.Player('player', {
            events: {
                'onReady': onPlayerReady,
                'onStateChange': onPlayerStateChange
            }
        });
    };

    function changePlaylist(tracks) {
        renderPlaylist(tracks);
        changeTrack(0);
    }

    function renderPlaylist(tracks) {
        elPlaylist.innerHTML = '';
        for (var i = 0; i < tracks.length; i++) {
            appendToPlaylist(tracks[i]);
        }
    }

    function resetPlaylist() {
        playlist = [];
        elPlaylist.innerHTML = '';
        trackSet = {};
        currentIndex = -1;
    }

    function appendToPlaylist(track) {
        if (trackSet[track.youtubeId])
            return;
        trackSet[track.youtubeId] = true;
        playlist.push(track);
        var index = elPlaylist.children.length;
        elPlaylist.innerHTML +=
            '<a class="playlist-item" data-playlist-idx="' + index + '">'+
                '<div class="playlist-item-index">' + (index + 1) + '</div>' +
                '<div class="playlist-item-now-playing">▶</div>' +
                '<div class="playlist-item-thumbnail"' +
                    'style="background-image: url(\''+ track.thumbnailUrl + '\')"></div>' +
                '<div class="playlist-item-title">' + track.name + '</div>' +
            '</a>';
    }

    var searchForm = $el('search-form');
    searchForm.addEventListener('submit', function (e) {
        e.preventDefault();
        resetPlaylist();
        spinner.style.display = 'block';
        if (eventSource) eventSource.close();
        eventSource = new EventSource('/tracks?q=' + searchForm.q.value);
        eventSource.addEventListener('song', function(e) {
            appendToPlaylist(JSON.parse(e.data));
        });
        eventSource.addEventListener('finish', function() {
            spinner.style.display = 'none';
            eventSource.close();
        });
    });

    function onPlayerReady(e) {
        changePlaylist(GLOBAL_PLAYLIST);
    }

    function changeTrack(idx) {
        var track = playlist[idx];
        var oldActive = $$('[aria-checked="true"]');
        if (oldActive)
            oldActive.removeAttribute('aria-checked');
        var plsItem = $$('[data-playlist-idx="' + idx + '"]');
        plsItem.setAttribute('aria-checked', 'true');
        document.title = track.name;
        player.loadVideoById(track.youtubeId, 0, 'default');
        currentIndex = idx;
    }

    function nextTrack() {
        if (currentIndex + 1 < playlist.length) {
            changeTrack(currentIndex + 1);
        } else {
            changeTrack(0);
        }
    }

    function onPlayerStateChange(e) {
        switch (e.data) {
            case YT.PlayerState.ENDED:
                nextTrack();
                break;
            case YT.PlayerState.UNSTARTED:
                if (previousVideoState == YT.PlayerState.BUFFERING) {
                    setTimeout(function() {
                        if (previousVideoState == YT.PlayerState.UNSTARTED) {
                            var brokenTrack = playlist[currentIndex];
                            reportBrokenTrack(brokenTrack);
                            nextTrack();
                        }
                    }, 4000);
                }
                break;
        }
        previousVideoState = e.data;
    }

    function reportBrokenTrack(track) {
        var req = new XMLHttpRequest();
        req.open('POST', '/broken-track');
        req.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
        req.send('name=' + track['name'] + '&youtube_id=' + track['youtubeId']);
    }

    $el('playlist-items').addEventListener('click', function(e) {
        if (e.target.matches('#playlist-items *')) {
            var plsItem = e.target;
            while (plsItem && !plsItem.matches('.playlist-item'))
                plsItem = plsItem.parentNode;
            if (plsItem) {
                var idx = plsItem.getAttribute('data-playlist-idx') - 0;
                changeTrack(idx);
            }
        }
    });

    $el('playlist-close').addEventListener('click', function(e) {
        document.body.classList.remove('playlist-open');
    });

    $el('menu').addEventListener('click', function(e) {
        document.body.classList.add('playlist-open');
    });

    document.body.addEventListener('keyup', function(e) {
       if (e.keyCode == 27)  /* pressed escape */
           document.body.classList.remove('playlist-open');
    });

    if (navigator.platform.indexOf('Win') > -1) {
        document.body.classList.add('win');
    }
})();
